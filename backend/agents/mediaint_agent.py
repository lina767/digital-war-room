"""
MEDIAINT — media intelligence from SOCMINT URLs: EXIF (GPS, camera, time), perceptual hashing,
and video keyframes (FFmpeg) feeding the same image pipeline.
"""

from __future__ import annotations

import io
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image
from PIL.ExifTags import IFD

from .utils import SourceResult, build_agent_meta, utc_now_iso

if TYPE_CHECKING:
    from .context import AgentContext

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; DigitalWarRoom-MEDIAINT/1.0)"
IMAGE_MAX_BYTES = int(os.getenv("MEDIAINT_IMAGE_MAX_BYTES", str(4 * 1024 * 1024)))
VIDEO_MAX_BYTES = int(os.getenv("MEDIAINT_VIDEO_MAX_BYTES", str(22 * 1024 * 1024)))
MAX_URLS = int(os.getenv("MEDIAINT_MAX_URLS", "14"))
MAX_VIDEO_FRAMES = int(os.getenv("MEDIAINT_MAX_VIDEO_FRAMES", "12"))
VIDEO_FRAME_INTERVAL_SEC = int(os.getenv("MEDIAINT_VIDEO_FRAME_INTERVAL_SEC", "5"))
PHASH_NEAR_DUP_THRESHOLD = int(os.getenv("MEDIAINT_PHASH_THRESHOLD", "12"))
VISION_MAX_CALLS = int(os.getenv("MEDIAINT_VISION_MAX_CALLS", "4"))


def _collect_media_urls_from_socmint(socmint: Dict[str, Any], limit: int) -> List[Tuple[str, str]]:
    """(url, provenance hint) from telegram/twitter/reddit posts."""
    out: List[Tuple[str, str]] = []
    seen: set = set()
    for key in ("telegram_posts", "twitter_posts", "reddit_posts"):
        for post in socmint.get(key) or []:
            if not isinstance(post, dict) or "error" in post:
                continue
            hint = f"{key}:{post.get('source', '')}"
            for u in post.get("media_urls") or []:
                if isinstance(u, str) and u.startswith("http") and u not in seen:
                    seen.add(u)
                    out.append((u, hint))
            for opt in ("thumbnail_url", "og_image"):
                u = post.get(opt)
                if isinstance(u, str) and u.startswith("http") and u not in seen:
                    seen.add(u)
                    out.append((u, f"{hint}:{opt}"))
            if len(out) >= limit:
                return out[:limit]
    return out[:limit]


def _get_socmint_dict(peers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if peers and isinstance(peers.get("socmint"), dict):
        return peers["socmint"]
    try:
        from .analysis_run_state import get_peer_result

        raw = get_peer_result("socmint")
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _is_probably_video(url: str, content_type: Optional[str]) -> bool:
    if content_type and "video/" in content_type.lower():
        return True
    lower = url.split("?", 1)[0].lower()
    return lower.endswith((".mp4", ".webm", ".mov", ".mkv", ".m4v"))


def _download_bytes(url: str, max_bytes: int) -> Tuple[Optional[bytes], Optional[str]]:
    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                ct = resp.headers.get("content-type")
                chunks: List[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(65536):
                    total += len(chunk)
                    if total > max_bytes:
                        return None, ct
                    chunks.append(chunk)
                return b"".join(chunks), ct
    except Exception as e:
        logger.debug("MEDIAINT download failed %s: %s", url[:80], e)
        return None, None


def _extract_exif_summary(im: Image.Image) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        exif = im.getexif()
        if not exif:
            return out
        from PIL.ExifTags import TAGS

        for tag_id, val in exif.items():
            name = TAGS.get(tag_id, tag_id)
            if name in ("Make", "Model", "DateTime", "DateTimeOriginal", "DateTimeDigitized"):
                out[name] = str(val) if val is not None else ""
        gps_ifd = exif.get_ifd(IFD.GPSInfo)
        if gps_ifd:
            lat, lon = _gps_to_latlon(gps_ifd)
            if lat is not None and lon is not None:
                out["GPSLatitude"] = round(lat, 6)
                out["GPSLongitude"] = round(lon, 6)
    except Exception as e:
        logger.debug("MEDIAINT EXIF: %s", e)
    return out


def _gps_to_latlon(gps_ifd: Dict[int, Any]) -> Tuple[Optional[float], Optional[float]]:
    def rat_to_float(x: Any) -> float:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, tuple) and len(x) >= 2:
            return float(x[0]) / float(x[1]) if x[1] else 0.0
        return 0.0

    try:
        lat_vals = gps_ifd.get(2)
        lat_ref = gps_ifd.get(1)
        lon_vals = gps_ifd.get(4)
        lon_ref = gps_ifd.get(3)
        if not lat_vals or not lon_vals:
            return None, None
        lat = rat_to_float(lat_vals[0]) + rat_to_float(lat_vals[1]) / 60.0 + rat_to_float(lat_vals[2]) / 3600.0
        lon = rat_to_float(lon_vals[0]) + rat_to_float(lon_vals[1]) / 60.0 + rat_to_float(lon_vals[2]) / 3600.0
        if isinstance(lat_ref, bytes):
            lat_ref = lat_ref.decode("ascii", errors="ignore")
        if isinstance(lon_ref, bytes):
            lon_ref = lon_ref.decode("ascii", errors="ignore")
        if lat_ref in ("S",):
            lat = -lat
        if lon_ref in ("W",):
            lon = -lon
        return lat, lon
    except Exception:
        return None, None


def _compute_phash(im: Image.Image) -> Optional[str]:
    try:
        import imagehash

        rgb = im.convert("RGB")
        return str(imagehash.phash(rgb))
    except Exception as e:
        logger.debug("MEDIAINT pHash: %s", e)
        return None


def _cluster_near_duplicate_indices(phashes: List[str], threshold: int) -> List[List[int]]:
    import imagehash

    objs: List[Any] = []
    valid_idx: List[int] = []
    for i, h in enumerate(phashes):
        if not h:
            continue
        try:
            objs.append(imagehash.hex_to_hash(h))
            valid_idx.append(i)
        except Exception:
            continue
    n = len(objs)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a in range(n):
        for b in range(a + 1, n):
            if objs[a] - objs[b] <= threshold:
                union(a, b)
    groups: Dict[int, List[int]] = {}
    for idx_a, orig_i in enumerate(valid_idx):
        r = find(idx_a)
        groups.setdefault(r, []).append(orig_i)
    return [g for g in groups.values() if len(g) > 1]


def _extract_video_keyframes(
    video_path: Path, work_dir: Path, interval_sec: int, max_frames: int
) -> List[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    out_pattern = str(work_dir / "kf_%04d.png")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval_sec}",
        "-frames:v",
        str(max_frames),
        out_pattern,
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120, capture_output=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        logger.info("MEDIAINT ffmpeg keyframes failed: %s", e)
        return []
    paths = sorted(work_dir.glob("kf_*.png"))
    return paths[:max_frames]


def _process_raster_image(
    data: bytes, source_url: str, provenance: str, kind: str
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "source_url": source_url[:500],
        "provenance": provenance[:200],
        "kind": kind,
    }
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        row["format"] = im.format or ""
        row["size"] = list(im.size)
        exif = _extract_exif_summary(im)
        if exif:
            row["exif"] = exif
        ph = _compute_phash(im)
        if ph:
            row["phash"] = ph
    except Exception as e:
        row["error"] = str(e)
    return row


def _apply_claude_vision(
    asset: Dict[str, Any],
    raw: bytes,
    conflict: str,
    calls_used: List[int],
    max_calls: int,
) -> None:
    """Attach ``vision_analysis`` via Claude Sonnet (see ``services.mediaint_vision_service``)."""
    if asset.get("error") or not raw:
        return
    if asset.get("kind") not in ("image", "video_keyframe"):
        return
    try:
        from services.mediaint_vision_service import maybe_analyze_osint_image

        exif = asset.get("exif") if isinstance(asset.get("exif"), dict) else None
        text = maybe_analyze_osint_image(
            raw,
            conflict=conflict or "",
            provenance=str(asset.get("provenance", "")),
            exif=exif,
            calls_used=calls_used,
            max_calls=max_calls,
        )
        if text:
            asset["vision_analysis"] = text[:8000]
    except Exception as e:
        logger.debug("MEDIAINT vision skipped: %s", e)


def _compute_mediaint_score(
    assets: List[Dict[str, Any]], dup_clusters: List[List[int]], video_frame_count: int
) -> float:
    gps_n = sum(
        1
        for a in assets
        if isinstance(a.get("exif"), dict) and "GPSLatitude" in a["exif"] and "GPSLongitude" in a["exif"]
    )
    score = 22.0
    score += min(28.0, len(assets) * 3.5)
    score += min(22.0, gps_n * 8.0)
    score += min(20.0, len(dup_clusters) * 7.0)
    score += min(15.0, video_frame_count * 1.2)
    vision_n = sum(1 for a in assets if a.get("vision_analysis"))
    score += min(14.0, vision_n * 3.5)
    return max(0.0, min(100.0, round(score, 1)))


def run_mediaint_agent(
    conflict: str,
    context: Optional["AgentContext"] = None,
    peers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _ = context
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    socmint = _get_socmint_dict(peers)
    pairs = _collect_media_urls_from_socmint(socmint, MAX_URLS)

    source_results: List[SourceResult] = [
        SourceResult(
            name="SOCMINT media",
            status="ok" if pairs else "error",
            fetched_at=fetched_at,
            record_count=len(pairs),
        )
    ]
    assets: List[Dict[str, Any]] = []
    video_frames_extracted = 0
    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    vision_calls_used: List[int] = [0]

    if not pairs:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "conflict": conflict,
            "mediaint_score": 12.0,
            "media_assets": [],
            "near_duplicate_clusters": [],
            "exif_gps_count": 0,
            "video_keyframes_extracted": 0,
            "vision_analysis_count": 0,
            "ffmpeg_available": ffmpeg_ok,
            "summary": "MEDIAINT: no media URLs in SOCMINT payload.",
            "_meta": build_agent_meta(
                "mediaint",
                fetched_at,
                duration_ms,
                source_results,
                fallback_used=True,
                has_any_data=False,
            ),
        }

    with tempfile.TemporaryDirectory(prefix="mediaint_") as tmp:
        tmp_path = Path(tmp)
        for url, prov in pairs:
            # Max size must not depend on ctype — it is only known after the download.
            max_bytes = VIDEO_MAX_BYTES if _is_probably_video(url, None) else IMAGE_MAX_BYTES
            data, ctype = _download_bytes(url, max_bytes)
            if not data:
                assets.append({"source_url": url[:500], "provenance": prov, "error": "download_failed"})
                continue
            if _is_probably_video(url, ctype):
                if not ffmpeg_ok:
                    assets.append(
                        {
                            "source_url": url[:500],
                            "provenance": prov,
                            "kind": "video",
                            "error": "ffmpeg_not_available",
                        }
                    )
                    continue
                vid_tag = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()[:12]
                vpath = tmp_path / f"vid_{vid_tag}.bin"
                vpath.write_bytes(data)
                vdir = tmp_path / f"frames_{vid_tag}"
                vdir.mkdir(exist_ok=True)
                frames = _extract_video_keyframes(
                    vpath, vdir, VIDEO_FRAME_INTERVAL_SEC, MAX_VIDEO_FRAMES
                )
                video_frames_extracted += len(frames)
                for j, fp in enumerate(frames):
                    try:
                        raw = fp.read_bytes()
                        sub = _process_raster_image(
                            raw, url, f"{prov}:frame{j}", "video_keyframe"
                        )
                        _apply_claude_vision(sub, raw, conflict, vision_calls_used, VISION_MAX_CALLS)
                        assets.append(sub)
                    except OSError:
                        continue
            else:
                img_asset = _process_raster_image(data, url, prov, "image")
                _apply_claude_vision(img_asset, data, conflict, vision_calls_used, VISION_MAX_CALLS)
                assets.append(img_asset)

    phashes = [str(a.get("phash") or "") for a in assets]
    clusters_idx = _cluster_near_duplicate_indices(phashes, PHASH_NEAR_DUP_THRESHOLD)
    dup_payload: List[Dict[str, Any]] = []
    for cl in clusters_idx:
        dup_payload.append(
            {
                "asset_indices": cl,
                "phashes": [phashes[i] for i in cl if i < len(phashes)],
            }
        )

    gps_count = sum(
        1
        for a in assets
        if isinstance(a.get("exif"), dict) and "GPSLatitude" in a["exif"]
    )
    score = _compute_mediaint_score(assets, clusters_idx, video_frames_extracted)
    vision_n = sum(1 for a in assets if a.get("vision_analysis"))
    if vision_n:
        source_results.append(
            SourceResult(
                name="Claude Vision (Sonnet, OSINT)",
                status="ok",
                fetched_at=fetched_at,
                record_count=vision_n,
            )
        )

    duration_ms = int((time.perf_counter() - start) * 1000)
    parts = [
        f"MEDIAINT processed {len(assets)} asset(s)",
        f"GPS {gps_count}",
        f"near-duplicate group(s) {len(clusters_idx)}",
    ]
    if video_frames_extracted:
        parts.append(f"video keyframes {video_frames_extracted}")
    if vision_n:
        parts.append(f"Claude Vision analyses {vision_n}")

    return {
        "conflict": conflict,
        "mediaint_score": score,
        "media_assets": assets[:40],
        "near_duplicate_clusters": dup_payload[:15],
        "exif_gps_count": gps_count,
        "video_keyframes_extracted": video_frames_extracted,
        "vision_analysis_count": vision_n,
        "ffmpeg_available": ffmpeg_ok,
        "summary": "; ".join(parts) + ".",
        "_meta": build_agent_meta(
            "mediaint",
            fetched_at,
            duration_ms,
            source_results,
            has_any_data=bool(assets),
        ),
    }
