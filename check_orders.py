import requests
import os
from datetime import datetime, timedelta

IMWEB_API_KEY = os.environ["IMWEB_API_KEY"]
IMWEB_SECRET_KEY = os.environ["IMWEB_SECRET_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

LOOKBACK_MINUTES = 11  # 10분 간격 실행 + 1분 여유


def get_access_token():
    res = requests.get(
        "https://api.imweb.me/v2/auth",
        params={"key": IMWEB_API_KEY, "secret": IMWEB_SECRET_KEY},
    )
    res.raise_for_status()
    data = res.json()
    if data.get("code") != 200:
        raise Exception(f"아임웹 인증 실패: {data}")
    return data["data"]["access_token"]


def get_recent_orders(access_token):
    now = datetime.now()
    cutoff = now - timedelta(minutes=LOOKBACK_MINUTES)

    res = requests.get(
        "https://api.imweb.me/v2/shop/orders",
        headers={"access-token": access_token},
        params={
            "start_date": cutoff.strftime("%Y-%m-%d"),
            "end_date": now.strftime("%Y-%m-%d"),
            "limit": 100,
            "page": 1,
        },
    )
    res.raise_for_status()
    data = res.json()

    if data.get("code") != 200:
        print(f"주문 조회 응답: {data}")
        return []

    orders = data.get("data", {}).get("list", [])

    # order_time이 Unix timestamp인 경우 필터링
    cutoff_ts = int(cutoff.timestamp())
    recent = []
    for order in orders:
        order_time = order.get("order_time", 0)
        if isinstance(order_time, (int, float)) and order_time >= cutoff_ts:
            recent.append(order)
        elif isinstance(order_time, str):
            # 문자열 형식 처리 (예: "2026-05-21 14:30:00")
            try:
                ot = datetime.strptime(order_time[:19], "%Y-%m-%d %H:%M:%S")
                if ot >= cutoff:
                    recent.append(order)
            except ValueError:
                recent.append(order)  # 파싱 실패 시 포함

    return recent


def format_order_message(order):
    order_code = order.get("order_code", "N/A")
    pay_price = order.get("pay_price", 0)
    orderer = order.get("orderer", {})
    orderer_name = orderer.get("name", "알 수 없음")

    items = order.get("items", [])
    item_names = [item.get("prod_name", "") for item in items[:3]]
    items_str = ", ".join(filter(None, item_names)) or "상품 정보 없음"
    if len(items) > 3:
        items_str += f" 외 {len(items) - 3}개"

    price_str = f"{int(pay_price):,}원"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "새 주문이 들어왔어요!"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*주문번호*\n{order_code}"},
                    {"type": "mrkdwn", "text": f"*결제금액*\n{price_str}"},
                    {"type": "mrkdwn", "text": f"*주문자*\n{orderer_name}"},
                    {"type": "mrkdwn", "text": f"*상품*\n{items_str}"},
                ],
            },
            {"type": "divider"},
        ]
    }


def send_slack(payload):
    res = requests.post(SLACK_WEBHOOK_URL, json=payload)
    res.raise_for_status()


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 주문 확인 시작")

    token = get_access_token()
    orders = get_recent_orders(token)

    print(f"최근 {LOOKBACK_MINUTES}분 신규 주문: {len(orders)}건")

    for order in orders:
        msg = format_order_message(order)
        send_slack(msg)
        print(f"알림 전송 완료: {order.get('order_code')}")

    if not orders:
        print("새 주문 없음")


if __name__ == "__main__":
    main()
