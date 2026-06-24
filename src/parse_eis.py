import os
import random
import ftplib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.config import (
    START_YEAR, END_YEAR, RAW_DATA_DIR, OUTPUT_FILE_PATH,
    FTP_HOST, FTP_USER, FTP_PASS, FTP_CWD_PATH,
    CUSTOMERS, CATEGORIES, SUPPLIERS_POOL
)


def test_real_ftp_connection():
    """
    Подключается к реальному FTP ЕИС и читает структуру папок закупок 223-ФЗ.
    """
    print("[INFO] Проверка доступности официального источника данных...")
    print(f"[INFO] Подключение к FTP ЕИС ({FTP_HOST}).")
    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=10)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.cwd(FTP_CWD_PATH)
        regions = ftp.nlst()[:3]
        print(f"📡 [FTP SUCCESS]Доступные директории регионов в ЕИС: {regions}")
        ftp.quit()
    except Exception as e:
        print(f"[FTP NOTICE] Официальный FTP ЕИС недоступен ({e}).")

def get_macro_factors(date):
    """Рассчитывает динамику курса валют и ставки ЦБ на основе даты лота."""
    year, month = date.year, date.month
    base_usd = 85.0 if year == 2024 else 93.0
    usd_rate = base_usd + (month * 0.8) + random.uniform(-2, 2)

    if year == 2024:
        rate_cb = 16.0 if month < 7 else 18.0 + (month - 7) * 0.8
    else:
        rate_cb = 21.0 + (month * 0.3)

    return round(usd_rate, 2), round(rate_cb, 1)


def generate_dataset(output_path):
    """Генерирует воспроизводимый массив данных на основе параметров из config.py."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    start_date = datetime(START_YEAR, 1, 1)
    end_date = datetime(END_YEAR, 12, 31)
    delta_days = (end_date - start_date).days

    records = []
    np.random.seed(42)
    random.seed(42)

    for i in range(500):
        pub_date = start_date + timedelta(days=random.randint(0, delta_days))
        cust_inn = random.choice(list(CUSTOMERS.keys()))
        cust_name = CUSTOMERS[cust_inn]

        if cust_name in ["АО СберТех", "ООО СБЕРБАНК-СЕРВИС"]:
            cat = "IT-оборудование и ПО"
        else:
            cat = random.choice(list(CATEGORIES.keys()))

        subject = random.choice(CATEGORIES[cat]) + f" (Лот №{random.randint(1, 10)})"

        if cat == "IT-оборудование и ПО":
            nmc = float(np.random.exponential(scale=15_000_000) + 500_000)
        elif cat == "Строительство и ремонты":
            nmc = float(np.random.normal(loc=40_000_000, scale=15_000_000))
        else:
            nmc = float(random.randint(300_000, 5_000_000))
        nmc = abs(round(nmc, 2))

        status = random.choice(["Размещение завершено", "Размещение завершено", "Отменена"])
        supplier_inn, supplier_name, final_price, participants_count = None, None, None, 0

        if status == "Размещение завершено":
            participants_count = random.choice([1, 2, 3, 4, 5])
            if cust_name == "АО СберТех" or random.random() < 0.15:
                winner = SUPPLIERS_POOL[3]
                participants_count = 1
            else:
                winner = random.choice(SUPPLIERS_POOL)

            supplier_inn = winner["inn"]
            supplier_name = winner["name"]
            final_price = nmc if participants_count == 1 else round(nmc * (1 - random.uniform(0.02, 0.25)), 2)

        usd_rate, rate_cb = get_macro_factors(pub_date)

        if supplier_name and "ИП" in supplier_name:
            supplier_name = "Физическое лицо / Индивидуальный предприниматель [ОБЕЗЛИЧЕНО]"
            supplier_inn = "77XXXXXXXX"

        records.append({
            "purchase_number": f"3240{random.randint(100000, 999999)}",
            "publish_date": pub_date.strftime("%Y-%m-%d"),
            "customer_inn": cust_inn, "customer_name": cust_name,
            "category": cat, "subject": subject, "nmc": nmc,
            "status": status, "participants_count": participants_count,
            "supplier_inn": supplier_inn, "supplier_name": supplier_name,
            "final_price": final_price, "usd_rate": usd_rate, "rate_cb": rate_cb
        })

    df = pd.DataFrame(records)

    duplicates = df.sample(n=15, random_state=42)
    df = pd.concat([df, duplicates], ignore_index=True)

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[SUCCESS] Сформирован воспроизводимый файл: {output_path} ({len(df)} строк)")


def main():

    print("Сбор данных и инициализация")
    test_real_ftp_connection()
    print("[INFO] Переключение на генерацию датасета ")
    generate_dataset(OUTPUT_FILE_PATH)


if __name__ == "__main__":
    main()