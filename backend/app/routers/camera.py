from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fastapi import HTTPException
from ..services.camera_service import gen_frames
from ..services.plate_tracker import plate_tracker

# no imports from main needed for now

router = APIRouter()


@router.get("/api/camera/stream/{gate_type}")
def video_feed(gate_type: str):
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="Invalid gate type")
    return StreamingResponse(gen_frames(gate_type),
                             media_type="multipart/x-mixed-replace; boundary=frame")




@router.get("/api/camera/tracking-status/{gate_type}")
def tracking_status(gate_type: str):
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="Invalid gate type")
    return plate_tracker.snapshot(gate_type)


