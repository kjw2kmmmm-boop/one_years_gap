from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import APIRouter, HTTPException, status, Depends, Header, Form

order = APIRouter(tags=['orders'])


@order.get('/orders', status_code=status.HTTP_200_OK, description='대시보드용 주문내역')
def get_orders():
    return 'orders'

@order.websocket('/ws/order-progress')
async def progress_order(websocket: WebSocket):
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            
            # 클라이언트에게 응답(Echo 또는 상태 전송)
            json_data = await websocket.send_json({
                "status": "COMPLETE",
                "message": "제조 완료",
                "received": data
            })


            if json_data['status'] == 'COMPLETE':
                await websocket.close()
            
    except WebSocketDisconnect:
        
        print("키오스크 웹소켓 연결 종료")

@order.post('/order', status_code=status.HTTP_201_CREATED, description='키오스크 주문넣기')
def push_order():
    return 