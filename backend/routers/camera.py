"""
Camera routes:
  POST /api/camera/photo          — Flutter enqueues photo request
  GET  /api/camera/photo/pending  — ground polls
  POST /api/camera/record         — Flutter toggles recording
  GET  /api/camera/record/pending — ground polls
  POST /api/camera/chunk          — ground uploads received LoRa chunk
  GET  /api/camera/latest         — Flutter fetches latest assembled photo
"""
import base64
import time
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/camera", tags=["camera"])


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


# ── In-memory state ───────────────────────────────────────────────────────────

_photo_pending = False
_rec_pending: bool | None = None

# Image assembly: {img_id: {"chunks": {seq: b64}, "total": int}}
_assemblies: dict[int, dict] = {}
_latest: dict | None = None   # {"id": int, "b64": str, "ts": float, "chunks": int}


# ── Photo command ─────────────────────────────────────────────────────────────

@router.post("/photo", status_code=status.HTTP_202_ACCEPTED)
async def request_photo(_: None = Depends(_verify_key)):
    global _photo_pending
    _photo_pending = True
    return {"queued": True}


@router.get("/photo/pending")
async def photo_pending(_: None = Depends(_verify_key)):
    global _photo_pending
    result = _photo_pending
    _photo_pending = False
    return {"pending": result}


# ── Recording command ─────────────────────────────────────────────────────────

class RecordIn(BaseModel):
    on: bool


@router.post("/record", status_code=status.HTTP_202_ACCEPTED)
async def request_record(body: RecordIn, _: None = Depends(_verify_key)):
    global _rec_pending
    _rec_pending = body.on
    return {"queued": True, "on": body.on}


@router.get("/record/pending")
async def record_pending(_: None = Depends(_verify_key)):
    global _rec_pending
    val = _rec_pending
    _rec_pending = None
    return {"pending": val is not None, "on": val}


# ── Chunk assembly ────────────────────────────────────────────────────────────

class ChunkIn(BaseModel):
    type: str   # "img"
    id: int
    seq: int
    tot: int
    data: str   # base64


@router.post("/chunk", status_code=status.HTTP_200_OK)
async def receive_chunk(body: ChunkIn, _: None = Depends(_verify_key)):
    global _latest

    img_id = body.id
    if img_id not in _assemblies:
        _assemblies[img_id] = {"chunks": {}, "total": body.tot}

    _assemblies[img_id]["chunks"][body.seq] = body.data
    _assemblies[img_id]["total"] = body.tot  # update in case first packet was lost

    received = len(_assemblies[img_id]["chunks"])
    total    = _assemblies[img_id]["total"]

    if received >= total:
        # All chunks present — assemble full JPEG
        ordered = [_assemblies[img_id]["chunks"][i] for i in range(total)]
        full_bytes = b"".join(base64.b64decode(c) for c in ordered)
        _latest = {
            "id":     img_id,
            "b64":    base64.b64encode(full_bytes).decode("ascii"),
            "ts":     time.time(),
            "chunks": total,
            "size":   len(full_bytes),
        }
        # Clean up assembly buffer, keep last 4 to handle retransmissions
        old_ids = sorted(_assemblies.keys())
        for old in old_ids[:-4]:
            del _assemblies[old]

    return {"id": img_id, "received": received, "total": total, "complete": received >= total}


# ── Latest image ──────────────────────────────────────────────────────────────

@router.get("/latest")
async def latest_image():
    if _latest is None:
        raise HTTPException(status_code=404, detail="No image available yet")
    return _latest


# ── Disk storage ──────────────────────────────────────────────────────────────

_storage: dict | None = None   # {"used_gb": float, "free_gb": float, "ts": float}


class StorageIn(BaseModel):
    used_gb: float
    free_gb: float


@router.post("/storage", status_code=status.HTTP_200_OK)
async def update_storage(body: StorageIn, _: None = Depends(_verify_key)):
    global _storage
    _storage = {
        "used_gb": round(body.used_gb, 2),
        "free_gb": round(body.free_gb, 2),
        "total_gb": round(body.used_gb + body.free_gb, 2),
        "used_pct": round(body.used_gb / max(body.used_gb + body.free_gb, 0.001) * 100, 1),
        "ts": time.time(),
    }
    return _storage


@router.get("/storage")
async def get_storage():
    if _storage is None:
        raise HTTPException(status_code=404, detail="No storage data yet")
    return _storage
