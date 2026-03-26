from typing import Any, Dict, List


def compute_sigint_score(aircraft: List[Dict[str, Any]], ships: List[Dict[str, Any]], reports: List[Dict[str, Any]]) -> float:
    """Compute SIGINT score in range 0-100."""
    base = 30.0
    base += min(40, sum(10 for a in aircraft if a.get("category") == "surveillance"))
    base += sum(8 for a in aircraft if a.get("category") == "tanker")
    base += sum(12 for a in aircraft if a.get("category") == "fighter")
    base += sum(6 for a in aircraft if a.get("category") == "transport")
    base += sum(8 for a in aircraft if a.get("category") == "iranian_gov")
    base += sum(1 for a in aircraft if a.get("category") == "doomsday") * 25
    base += min(25, len(ships) * 5)
    base += min(30, len(reports) * 8)
    return max(0.0, min(100.0, base))
