import pandas as pd
import psycopg2
from psycopg2 import extras

from src.config import DB_CONFIG, OUTPUT_FILE_PATH


def run_stage_2():
    print("Этап 2, очистка и миграция в PostgresSQL")
    print(f"[INFO] Чтение файла: {OUTPUT_FILE_PATH}")
    try:
        df = pd.read_csv(OUTPUT_FILE_PATH)
    except FileNotFoundError:
        print(f" Ошибка: Файл {OUTPUT_FILE_PATH} не найден")
        return

    total_before = len(df)

    duplicate_mask = df.duplicated(subset=['purchase_number'], keep='first')
    duplicate_count = duplicate_mask.sum()

    print(f"[INFO] Успешно прочитано строк из CSV: {total_before}")
    print(f"[СТАТИСТИКА ПО ДУБЛЯМ] Найдено избыточных дубликатов: {duplicate_count}")


    df_clean = df.drop_duplicates(subset=['purchase_number'], keep='first').copy()
    print(f"[INFO] Уникальные лоты: {len(df_clean)}")

    df_clean['participants_count'] = df_clean['participants_count'].fillna(0).astype(int)
    df_clean['supplier_inn'] = df_clean['supplier_inn'].fillna('NOT_FOUND')
    df_clean['supplier_name'] = df_clean['supplier_name'].fillna('Нет победителя / Торги не состоялись')
    df_clean['final_price'] = df_clean['final_price'].fillna(0.0)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("[INFO] Создание реляционной структуры таблиц ")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dict_customers
            (
                customer_inn VARCHAR(20) PRIMARY KEY,
                customer_name TEXT NOT NULL
            );
        """)

        # Справочник поставщиков
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dict_suppliers
            (
                supplier_inn VARCHAR(20) PRIMARY KEY,
                supplier_name TEXT NOT NULL
            );
        """)

        # Таблица фактов закупок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchases
            (
                purchase_number VARCHAR(30) PRIMARY KEY,
                publish_date DATE NOT NULL,
                customer_inn VARCHAR(20) REFERENCES dict_customers(customer_inn),
                supplier_inn VARCHAR(20) REFERENCES dict_suppliers(supplier_inn),
                category VARCHAR(100) NOT NULL,
                subject TEXT NOT NULL,
                nmc NUMERIC(15, 2) NOT NULL,
                final_price NUMERIC(15, 2) NOT NULL,
                status VARCHAR(50) NOT NULL,
                participants_count INT NOT NULL,
                usd_rate NUMERIC(10, 2),
                rate_cb NUMERIC(5, 2)
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(publish_date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchases_category ON purchases(category);")

        # 3. Нормализация и вставка данных
        print("[INFO] Выделение справочников и пакетная вставка")

        unique_cust = df_clean[['customer_inn', 'customer_name']].drop_duplicates()
        extras.execute_values(
            cursor,
            "INSERT INTO dict_customers (customer_inn, customer_name) VALUES %s ON CONFLICT (customer_inn) DO NOTHING;",
            list(unique_cust.itertuples(index=False, name=None))
        )

        unique_supp = df_clean[['supplier_inn', 'supplier_name']].drop_duplicates()
        extras.execute_values(
            cursor,
            "INSERT INTO dict_suppliers (supplier_inn, supplier_name) VALUES %s ON CONFLICT (supplier_inn) DO NOTHING;",
            list(unique_supp.itertuples(index=False, name=None))
        )

        # Заполняем основную таблицу purchases
        purchases_data = [
            (
                row.purchase_number, row.publish_date, row.customer_inn, row.supplier_inn,
                row.category, row.subject, row.nmc, row.final_price, row.status,
                row.participants_count, row.usd_rate, row.rate_cb
            )
            for row in df_clean.itertuples(index=False)
        ]

        extras.execute_values(
            cursor,
            """
            INSERT INTO purchases (purchase_number, publish_date, customer_inn, supplier_inn, category, subject,
                                   nmc, final_price, status, participants_count, usd_rate, rate_cb)
            VALUES %s ON CONFLICT (purchase_number) DO NOTHING;
            """,
            purchases_data
        )

        conn.commit()
        print("[УСПЕХ]")

    except Exception as e:
        print(f"Ошибка СУБД: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    run_stage_2()