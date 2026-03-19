"""
Document ingest and QA routes (PDF, RAG).
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from middleware.rate_limit import limiter

router = APIRouter()


class DocumentIngestRequest(BaseModel):
    url: str
    source: str = "pdf"
    conflict: str = ""


class DocumentQARequest(BaseModel):
    question: str
    source: Optional[str] = None
    conflict: Optional[str] = None
    doc_id: Optional[str] = None


@router.post("/documents/ingest")
@limiter.limit("10/minute")
async def ingest_document(request: Request, body: DocumentIngestRequest):
    """
    POST /documents/ingest
    Download and ingest a PDF document for Document QA.
    """
    try:
        from services.pdf_ingest_service import ingest_pdf

        result = await ingest_pdf(
            url=body.url,
            source=body.source,
            conflict=body.conflict,
        )
        if result:
            return result
        return JSONResponse(
            status_code=422,
            content={"error": "Failed to ingest PDF — download or text extraction failed"},
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/documents")
async def list_documents():
    """GET /documents — List all ingested documents."""
    try:
        from services.pdf_ingest_service import list_documents as _list

        return _list()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/documents/qa")
@limiter.limit("30/minute")
async def document_qa(request: Request, body: DocumentQARequest):
    """
    POST /documents/qa
    Ask a question over ingested PDF documents.
    Uses semantic search to find relevant chunks, then Haiku (primary)
    or HF extractive QA (fallback) to answer.
    """
    try:
        from services.pdf_ingest_service import find_relevant_chunks, get_chunks

        if body.doc_id:
            chunks = get_chunks(body.doc_id)
            if not chunks:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Document {body.doc_id} not found or has no chunks"},
                )
        else:
            relevant = await find_relevant_chunks(
                body.question,
                source=body.source,
                conflict=body.conflict,
                top_k=5,
            )
            chunks = [r.get("text_preview", "") for r in relevant if r.get("text_preview")]

        if not chunks:
            return {"answer": "No relevant documents found.", "confidence": 0, "sources": []}

        try:
            from services.haiku_service import document_qa as haiku_qa

            result = await haiku_qa(body.question, chunks, max_chunks=5)
            if result and result.get("answer"):
                return result
        except Exception:
            pass

        try:
            from services.hf_service import document_qa_multi

            hf_results = await document_qa_multi(body.question, chunks, top_k=3)
            if hf_results:
                return {
                    "answer": hf_results[0].get("answer", ""),
                    "confidence": hf_results[0].get("score", 0),
                    "sources": [f"chunk_{r.get('chunk_index', '?')}" for r in hf_results],
                    "all_answers": hf_results,
                }
        except Exception:
            pass

        return {"answer": "Could not process the question.", "confidence": 0, "sources": []}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
