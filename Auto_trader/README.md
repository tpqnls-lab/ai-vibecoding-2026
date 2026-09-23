# v0.1 실행

```powershell
python -m pip install -r requirements.txt
python -m auto_trader
```

브라우저에서 `http://127.0.0.1:8000/docs`를 열면 Swagger UI를 사용할 수 있다.
`http://127.0.0.1:8000/`에서는 2단계 대시보드가 열린다. `.env`에 토스증권 Client ID와 Secret을 설정하면 현재가를 자동 조회하고 WebSocket으로 화면을 갱신한다.

```env
TOSS_CLIENT_ID=발급받은_client_id
TOSS_CLIENT_SECRET=발급받은_client_secret
TOSS_SYMBOLS=005930,000660
TOSS_PRICE_INTERVAL=2
```

시세 조회는 토큰을 자동 발급/갱신하여 `GET /api/v1/prices`를 호출한다. 토큰과 Client Secret은 브라우저로 보내지 않는다.

v0.1은 토스증권 실거래 API를 호출하지 않는 `PAPER`/`DRY_RUN` 프로토타입이다. 가격을 등록한 뒤 주문을 요청한다.

```powershell
Invoke-RestMethod -Method Put 'http://127.0.0.1:8000/api/v1/market/prices/005930?price=70000'
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/v1/orders' -ContentType 'application/json' -Body '{"symbol":"005930","side":"BUY","quantity":"10","price":"70000"}'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/portfolio'
```
