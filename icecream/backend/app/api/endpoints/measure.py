from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import APIRouter, HTTPException, status, Depends, Header, Form

measure = APIRouter(tags=['orders'])


@measure.get('/measure', status_code=status.HTTP_200_OK, description='현재 측정된 컵 크기')
async def get_measure():
    return 'measure'

@measure.websocket('/ws/measuring')
async def measure_cup(websocket: WebSocket):
    await websocket.accept()
        
    try:
        while True:
            data = await websocket.receive_text()
            
            # 클라이언트에게 응답(Echo 또는 상태 전송)
            json_data = await websocket.send_json({
                "status": "COMPLETE",
                "message": "측정 중",
                "received": data,
                "dummy" : {"z": 140, "diameter": 100}
            })


            if json_data['status'] == 'COMPLETE':
                await websocket.close()
            
    except WebSocketDisconnect:
        
        print("키오스크 웹소켓 연결 종료")
    


#@measure.post('/measure-cup', status_code=status.HTTP_201_CREATED, description='컵 측정하기')
#def measure_cup():
#    return '컵 측정중'