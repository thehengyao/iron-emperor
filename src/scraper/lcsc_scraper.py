"""
立创商城 (LCSC) 零件爬虫 — 使用 立创EDA Pro 开放 API。

API: https://pro.easyeda.com/api/eda/product/search
无需登录，价格单位 CNY（¥），数据来自立创商城真实库存。

Usage:
    python3 src/scraper/lcsc_scraper.py
    python3 src/scraper/lcsc_scraper.py --resume
    python3 src/scraper/lcsc_scraper.py --keyword "ESP32"
"""
import argparse
import json
import sqlite3
import time
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.db.schema import init_db, DB_PATH

API_URL = "https://pro.easyeda.com/api/eda/product/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://pro.easyeda.com/editor",
    "Origin": "https://pro.easyeda.com",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

# 覆盖常用分类关键词
KEYWORDS = [
    "ESP32", "ESP8266", "STM32F103", "STM32F4", "Arduino Nano",
    "RP2040", "ATmega328", "nRF52840", "CH340", "CP2102",
    "MPU6050", "BME280", "DHT11", "DHT22", "AHT20",
    "DS18B20", "BMP280", "SHT31", "LM393", "LM358",
    "HC-SR04", "PIR sensor", "MQ-2", "soil moisture",
    "OV2640", "OV7670", "GC0308",
    "SSD1306 OLED", "ILI9341", "ST7789", "LCD 1602",
    "A4988 stepper", "DRV8825", "L298N", "TB6600",
    "MG996R servo", "SG90 servo",
    "TP4056", "BMS 18650", "IP5306", "XL4016", "MT3608",
    "LM7805", "AMS1117 3.3", "XL6009",
    "NRF24L01", "HC-05 bluetooth", "HC-06", "SIM800L", "SIM7600",
    "W5500", "ENC28J60",
    "WS2812B RGB", "SK6812",
    "IR receiver 1838", "IR transmitter",
    "relay module 5V", "relay module 3.3V",
    "PCF8574", "MCP23017",
    "HX711 load cell", "MAX30102", "AD8232 ECG",
    "SD card module", "micro SD",
    "RTC DS3231", "RTC DS1307",
    "rotary encoder", "hall sensor",
    "buzzer active", "buzzer passive",
    "USB Type-C connector", "micro USB connector",
    "XH2.54 connector", "JST connector",
    "100nF capacitor", "10uF capacitor", "100uF capacitor",
    "10k resistor", "1k resistor", "4.7k resistor",
    "1N4007 diode", "Schottky diode",
    "NPN transistor S8050", "PNP transistor S8550",
    "IRFZ44N MOSFET", "2N7000 MOSFET",
    "push button switch", "tactile switch",
    "LED 5mm red", "LED 5mm green", "LED 5mm blue",
    "crystal 8MHz", "crystal 16MHz", "crystal 12MHz",
    "LDO regulator", "DC-DC buck",
    "fuse holder", "polyfuse",
    "pin header 2.54", "female header 2.54",
    "screw terminal", "KF301",
]


def _proxies() -> dict | None:
    """Pick up system proxy if set (e.g. Clash/V2Ray on 7897)."""
    import os
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    return {"https": proxy, "http": proxy} if proxy else None


def search(keyword: str, page: int = 1, page_size: int = 50) -> dict:
    params = {
        "keyword": keyword,
        "currentPage": page,
        "pageSize": page_size,
    }
    import warnings
    from urllib3.exceptions import InsecureRequestWarning
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)
    resp = requests.get(API_URL, params=params, headers=HEADERS,
                        timeout=15, proxies=_proxies(), verify=False)
    resp.raise_for_status()
    return resp.json()


def parse_product(item: dict) -> dict | None:
    try:
        # Price: take 1-piece CNY price
        price_cny = None
        price_tiers = item.get("price", [])
        if price_tiers and isinstance(price_tiers[0], list):
            price_cny = float(price_tiers[0][1])
        elif item.get("priceList"):
            price_cny = float(item["priceList"][0].get("price", 0) or 0)

        lcsc_num = item.get("number", "")  # e.g. C277944
        mpn = item.get("mpn", "")
        name = mpn or lcsc_num
        url = f"https://www.lcsc.com/product-detail/{lcsc_num}.html" if lcsc_num else ""
        if not name or not url:
            return None

        manufacturer = item.get("manufacturer", "")
        package = item.get("package", "")
        description = f"{manufacturer} {mpn} {package}".strip()

        # Specs from device_info
        attrs = item.get("device_info", {}).get("attributes", {})
        specs = {k: v for k, v in attrs.items() if v and k not in ("Symbol", "Footprint", "3D Model")}

        image = None
        images = item.get("image", [])
        if images:
            image = images[0].get("224x224") or images[0].get("96x96")

        category = attrs.get("LCSC Part Name", item.get("catalogName", ""))

        return {
            "name": name,
            "sku": lcsc_num,
            "url": url,
            "price": round(price_cny, 4) if price_cny else None,
            "currency": "CNY",
            "in_stock": 1,
            "description": description[:500],
            "specs": json.dumps(specs, ensure_ascii=False) if specs else None,
            "image_url": image,
            "category": category,
        }
    except Exception:
        return None


def get_or_create_category(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO categories (name, url) VALUES (?, ?)",
                 (name, f"https://pro.easyeda.com/components?keyword={name}"))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def upsert_part(conn: sqlite3.Connection, part: dict, category_id: int):
    conn.execute(
        """INSERT INTO parts (name, url, sku, price, currency, in_stock, description, specs, image_url, category_id)
           VALUES (:name, :url, :sku, :price, :currency, :in_stock, :description, :specs, :image_url, :cat)
           ON CONFLICT(url) DO UPDATE SET
               price=excluded.price,
               in_stock=excluded.in_stock,
               description=excluded.description,
               specs=excluded.specs,
               image_url=excluded.image_url""",
        {**part, "cat": category_id},
    )


def rebuild_fts(conn: sqlite3.Connection):
    print("Rebuilding FTS5 index...")
    conn.execute('INSERT INTO parts_fts(parts_fts) VALUES("rebuild")')
    conn.commit()
    print("FTS5 rebuilt.")


def scrape(keywords: list[str], conn: sqlite3.Connection, resume_file: Path):
    done = set(resume_file.read_text().strip().splitlines()) if resume_file.exists() else set()
    total = 0

    for keyword in keywords:
        if keyword in done:
            print(f"  [skip] {keyword}")
            continue
        print(f"\nScraping: {keyword}")
        inserted = 0
        for page in range(1, 6):  # max 5 pages per keyword
            try:
                data = search(keyword, page=page, page_size=50)
            except Exception as e:
                print(f"  ⚠ {e}")
                break

            result = data.get("result", {})
            products = result.get("productList", [])
            if not products:
                break

            cat_id = get_or_create_category(conn, keyword)
            for item in products:
                part = parse_product(item)
                if part:
                    try:
                        upsert_part(conn, part, cat_id)
                        inserted += 1
                    except Exception:
                        pass
            conn.commit()
            print(f"  Page {page}: +{len(products)} products")

            total_count = result.get("total", 0)
            if page * 50 >= min(total_count, 250):
                break
            time.sleep(0.3)

        print(f"  ✅ {keyword}: {inserted} parts")
        total += inserted
        with open(resume_file, "a") as f:
            f.write(keyword + "\n")
        done.add(keyword)

    print(f"\n{'='*40}")
    print(f"Total: {total} parts")
    rebuild_fts(conn)


def main():
    parser = argparse.ArgumentParser(description="焊武帝 — 立创商城零件爬虫")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keyword", type=str)
    args = parser.parse_args()

    conn = init_db(DB_PATH)
    resume_file = Path("lcsc_scrape_progress.txt")
    keywords = [args.keyword] if args.keyword else KEYWORDS

    if not args.resume and not args.keyword and resume_file.exists():
        resume_file.unlink()

    print("焊武帝 IronEmperor — LCSC Scraper (via 立创EDA Pro API)")
    print(f"Keywords: {len(keywords)} | DB: {DB_PATH}")
    scrape(keywords, conn, resume_file)


if __name__ == "__main__":
    main()
