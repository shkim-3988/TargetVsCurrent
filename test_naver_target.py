import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

url = "https://finance.naver.com/item/main.naver?code=005930"

r = requests.get(url, headers=headers, timeout=5)

print("HTTP Status:", r.status_code)

# HTML 저장
with open("naver_samsung.html", "w", encoding="utf-8") as f:
    f.write(r.text)

print("HTML saved to naver_samsung.html")
