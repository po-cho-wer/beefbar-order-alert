import requests
import os
import json
from datetime import datetime, timedelta, timezone

IMWEB_API_KEY = os.environ["IMWEB_API_KEY"]
IMWEB_SECRET_KEY = os.environ["IMWEB_SECRET_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

LOOKBACK_DAYS = 2  # 최근 2일치 조회 (Actions 실행 간격 무관하게 안전하게)
SENT_ORDERS_FILE = "sent_orders.json"
KST = timezone(timedelta(hours=9))


def get_access_token():
    res = requests.get(
        "https://api.imweb.me/v2/auth",
        params={"key": IMWEB_API_KEY, "secret": IMWEB_SECRET_KEY},
    )
    res.raise_for_status()
    data = res.json()
    if data.get("code") != 200:
        raise Exception(f"아임웹 인증 실패: {data}")
    if "data" in data:
        return data["data"]["access_token"]
    return data["access_token"]


def load_sent_orders():
    if os.path.exists(SENT_ORDERS_FILE):
        with open(SENT_ORDERS_FILE) as f:
            return set(json.load(f))
    return set()


def save_sent_orders(sent):
    with open(SENT_ORDERS_FILE, "w") as f:
        json.dump(list(sent), f)


def get_recent_orders(access_token):
    now_kst = datetime.now(timezone.utc).astimezone(KST)
    start_kst = (now_kst - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end_kst = now_kst.strftime("%Y-%m-%d")

    res = requests.get(
        "https://api.imweb.me/v2/shop/orders",
        headers={"access-token": access_token},
        params={
            "start_date": start_kst,
            "end_date": end_kst,
            "limit": 100,
            "page": 1,
        },
    )
    res.raise_for_status()
    data = res.json()

    if data.get("code") != 200:
        print(f"주문 조회 응답: {data}")
        return []

    return data.get("data", {}).get("list", [])


PAY_TYPE_LABELS = {
    "npay": "네이버페이",
    "kakaopay": "카카오페이",
    "card": "신용카드",
    "bank": "계좌이체",
    "vbank": "가상계좌",
    "phone": "휴대폰결제",
    "point": "포인트",
    "free": "무료",
}


def format_order_message(order):
    order_code = order.get("order_code", "N/A")
    orderer = order.get("orderer", {})
    orderer_name = orderer.get("name", "알 수 없음")

    payment = order.get("payment", {})
    total_price = payment.get("total_price", 0)        # 상품 금액
    deliv_price = payment.get("deliv_price", 0)        # 배송비
    payment_amount = payment.get("payment_amount", 0)  # 최종 결제금액
    pay_type = payment.get("pay_type", "")
    pay_type_label = PAY_TYPE_LABELS.get(pay_type, pay_type or "알 수 없음")

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
                    {"type": "mrkdwn", "text": f"*주문자*\n{orderer_name}"},
                    {"type": "mrkdwn", "text": f"*결제금액*\n{int(payment_amount):,}원 (배송비 {int(deliv_price):,}원 포함)"},
                    {"type": "mrkdwn", "text": f"*결제수단*\n{pay_type_label}"},
                ],
            },
            {"type": "divider"},
        ]
    }


def send_slack(payload):
    res = requests.post(SLACK_WEBHOOK_URL, json=payload)
    res.raise_for_status()


def main():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST] 주문 확인 시작")

    sent_orders = load_sent_orders()
    print(f"이미 처리된 주문 수: {len(sent_orders)}건")

    token = get_access_token()
    orders = get_recent_orders(token)
    print(f"API 반환 주문 수: {len(orders)}건")

    new_count = 0
    for order in orders:
        order_code = order.get("order_code", "")
        if not order_code or order_code in sent_orders:
            continue
        msg = format_order_message(order)
        send_slack(msg)
        sent_orders.add(order_code)
        new_count += 1
        print(f"알림 전송: {order_code}")

    save_sent_orders(sent_orders)
    print(f"신규 알림 전송: {new_count}건")


if __name__ == "__main__":
    main()
