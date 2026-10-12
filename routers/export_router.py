from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_current_user
from models.user import User
from services.export_service import get_task_view

router = APIRouter(prefix="/export", tags=["export"])


# 前端导出卡片轮询用。统计摘要是给模型的，卡片只要解读文字
@router.get("/tasks/{task_id}")
async def get_export_task(task_id: str, user: User = Depends(get_current_user)):
    view = await get_task_view(task_id, user.id)
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导出任务不存在")
    view.pop("summary")
    return view
