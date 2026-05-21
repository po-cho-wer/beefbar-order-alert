import requests
import os
from datetime import datetime, timedelta

IMWEB_API_KEY = os.environ["IMWEB_API_KEY"]
IMWEB_SECRET_KEY = os.environ["IMWEB_SECRET_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

CANCEL_STATUSES = {"cancel_request", "cancel", "cancel_done", "refund_request", "refund", "refund_done"}


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


def get_weekly_orders(access_token):
    # 지난 주 월요일 00:00 ~ 일요일 23:59 (KST 기준으로 날짜 계산)
    today = datetime.utcnow() + timedelta(hours=9)  # KST
    last_monday = today - timedelta(days=7)
    last_sunday = today - timedelta(days=1)

    start_date = last_monday.strftime("%Y-%m-%d")
    end_date = last_sunday.strftime("%Y-%m-%d")

    print(f"조회 기간: {start_date} ~ {end_date}")

    all_orders = []
    page = 1
    while True:
        res = requests.get(
            "https://api.imweb.me/v2/shop/orders",
            headers={"access-token": access_token},
            params={
                "start_date": start_date,
                "end_date": end_date,
                "limit": 100,
                "page": page,
            },
        )
        res.raise_for_status()
        data = res.json()

        if data.get("code") != 200:
            print(f"주문 조회 응답: {data}")
            break

        orders = data.get("data", {}).get("list", [])
        all_orders.extend(orders)

        # 페이지가 더 없으면 종료
        total_count = data.get("data", {}).get("total_count", 0)
        if len(all_orders) >= total_count or not orders:
            break
        page += 1

    return all_orders, start_date, end_date


def calculate_summary(orders):
    total_orders = 0
    cancel_orders = 0
    total_revenue = 0

    for order in orders:
        status = str(order.get("order_status", "")).lower()
        pay_price = order.get("pay_price", 0) or 0

        if status in CANCEL_STATUSES:
            cancel_orders += 1
        else:
            total_orders += 1
            total_revenue += int(pay_price)

    return total_orders, cancel_orders, total_revenue


def send_weekly_summary(total_orders, cancel_orders, total_revenue, start_date, end_date):
    period = f"{start_date} ~ {end_date}"
    revenue_str = f"{total_revenue:,}원"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "주간 주문 리포트"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{period}* 한 주간 결과입니다."},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*주문 수*\n{total_orders}건"},
                    {"type": "mrkdwn", "text": f"*취소/환불*\n{cancel_orders}건"},
                    {"type": "mrkdwn", "text": f"*매출*\n{revenue_str}"},
                ],
            },
            {"type": "divider"},
        ]
    }

    res = requests.post(SLACK_WEBHOOK_URL, json=payload)
    res.raise_for_status()


def main():
    print(f"[{datetime.utcnow() + timedelta(hours=9):%Y-%m-%d %H:%M:%S}] 주간 리포트 시작")

    token = get_access_token()
    orders, start_date, end_date = get_weekly_orders(token)

    print(f"조회된 주문 수: {len(orders)}건")

    total_orders, cancel_orders, total_revenue = calculate_summary(orders)
    send_weekly_summary(total_orders, cancel_orders, total_revenue, start_date, end_date)

    print(f"리포트 전송 완료 — 주문 {total_orders}건 / 취소 {cancel_orders}건 / 매출 {total_revenue:,}원")


if __name__ == "__main__":
    main()
