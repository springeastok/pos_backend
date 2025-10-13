from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
import os
import json
import base64

app = FastAPI(title="POS System API")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# データベース接続設定
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'), 
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'pos_system'),
    'port': int(os.getenv('DB_PORT', 3306))
}

def get_db_connection():
    """データベース接続を取得"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# ===== Pydanticモデル =====

class ProductResponse(BaseModel):
    PRD_ID: int
    CODE: int
    NAME: str
    PRICE: int
    stock_quantity: Optional[int] = None

class ECStockResponse(BaseModel):
    CODE: int
    NAME: str
    std_PRICE: int
    ec_stock_quantity: int

class CartItem(BaseModel):
    PRD_ID: int
    CODE: int
    NAME: str
    PRICE: int
    quantity: int
    subtotal: int

class QRCodeRequest(BaseModel):
    items: List[CartItem]
    total_amount: int

class QRCodeResponse(BaseModel):
    qr_data: str
    pending_transaction_id: int

class PaymentRequest(BaseModel):
    qr_data: str
    payment_method: str  # 'cash', 'credit', 'qr', 'emoney'
    cash_received: Optional[int] = None

class PaymentResponse(BaseModel):
    transaction_id: int
    total_amount: int
    change_amount: Optional[int] = None
    payment_method: str
    items: List[dict]

# ===== APIエンドポイント =====

@app.get("/")
def read_root():
    """APIのヘルスチェック"""
    return {"status": "ok", "message": "POS System API is running"}

@app.get("/api/products/search/{code}", response_model=ProductResponse)
def search_product_by_code(code: int):
    """バーコードで商品を検索"""
    print(f"\n{'='*50}")
    print(f"DEBUG: Searching for code: {code}")
    print(f"DEBUG: Code type: {type(code)}")
    print(f"{'='*50}\n")
    
    try:
        conn = get_db_connection()
        print("DEBUG: Database connection successful")
    except Exception as e:
        print(f"DEBUG: Database connection FAILED: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = "SELECT * FROM store_products WHERE CODE = %s"
        print(f"DEBUG: Executing query: {query}")
        print(f"DEBUG: Query parameter: {code}")
        
        cursor.execute(query, (code,))
        product = cursor.fetchone()
        
        print(f"DEBUG: Query executed successfully")
        print(f"DEBUG: Result: {product}")
        
        if not product:
            print("DEBUG: Product not found (404)")
            raise HTTPException(status_code=404, detail="Product not found")
        
        print("DEBUG: Returning product data")
        return product
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n{'!'*50}")
        print(f"DEBUG: EXCEPTION occurred!")
        print(f"DEBUG: Error type: {type(e).__name__}")
        print(f"DEBUG: Error message: {str(e)}")
        print(f"{'!'*50}\n")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
        print("DEBUG: Database connection closed\n")

@app.get("/api/products/ec-stock/{code}", response_model=ECStockResponse)
def get_ec_stock(code: int):
    """EC在庫を確認"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = "SELECT * FROM headquarters_products WHERE CODE = %s"
        cursor.execute(query, (code,))
        product = cursor.fetchone()
        
        if not product:
            raise HTTPException(status_code=404, detail="Product not found in EC system")
        
        return product
    finally:
        cursor.close()
        conn.close()

@app.post("/api/qrcode/generate", response_model=QRCodeResponse)
def generate_qr_code(request: QRCodeRequest):
    """レジモードから会計用QRコードを生成"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # 仮トランザクションを作成(支払い前の状態)
        insert_transaction = """
            INSERT INTO sales_transactions 
            (total_amount, payment_method, is_pending)
            VALUES (%s, 'pending', TRUE)
        """
        cursor.execute(insert_transaction, (request.total_amount,))
        pending_transaction_id = cursor.lastrowid
        
        # 仮明細を登録
        for item in request.items:
            insert_detail = """
                INSERT INTO sales_details 
                (transaction_id, PRD_ID, CODE, NAME, PRICE, quantity, subtotal)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_detail, (
                pending_transaction_id,
                item.PRD_ID,
                item.CODE,
                item.NAME,
                item.PRICE,
                item.quantity,
                item.subtotal
            ))
        
        conn.commit()
        
        # QRコード用データを作成(JSON → Base64エンコード)
        qr_payload = {
            'transaction_id': pending_transaction_id,
            'total_amount': request.total_amount,
            'items': [item.dict() for item in request.items],
            'timestamp': datetime.now().isoformat()
        }
        
        qr_data = base64.b64encode(json.dumps(qr_payload).encode()).decode()
        
        return {
            'qr_data': qr_data,
            'pending_transaction_id': pending_transaction_id
        }
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/payment/process", response_model=PaymentResponse)
def process_payment(payment: PaymentRequest):
    """タブレットモードからQRコードを読み取って支払い処理"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # QRデータをデコード
        try:
            decoded_data = base64.b64decode(payment.qr_data.encode()).decode()
            qr_payload = json.loads(decoded_data)
        except:
            raise HTTPException(status_code=400, detail="Invalid QR code data")
        
        transaction_id = qr_payload['transaction_id']
        total_amount = qr_payload['total_amount']
        items = qr_payload['items']
        
        conn.start_transaction()
        
        # トランザクション存在確認
        cursor.execute(
            "SELECT * FROM sales_transactions WHERE transaction_id = %s AND is_pending = TRUE",
            (transaction_id,)
        )
        transaction = cursor.fetchone()
        
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found or already processed")
        
        # お釣り計算(現金の場合)
        change_amount = None
        if payment.payment_method == 'cash':
            if not payment.cash_received or payment.cash_received < total_amount:
                raise HTTPException(status_code=400, detail="Insufficient cash received")
            change_amount = payment.cash_received - total_amount
        
        # トランザクションを確定(is_pending = FALSE)
        update_transaction = """
            UPDATE sales_transactions 
            SET payment_method = %s, 
                cash_received = %s, 
                change_amount = %s,
                is_pending = FALSE,
                transaction_date = NOW()
            WHERE transaction_id = %s
        """
        cursor.execute(update_transaction, (
            payment.payment_method,
            payment.cash_received,
            change_amount,
            transaction_id
        ))
        
        # 在庫を減らす
        for item in items:
            update_stock = """
                UPDATE store_products 
                SET stock_quantity = stock_quantity - %s 
                WHERE PRD_ID = %s
            """
            cursor.execute(update_stock, (item['quantity'], item['PRD_ID']))
            
            # 在庫チェック
            cursor.execute(
                "SELECT stock_quantity FROM store_products WHERE PRD_ID = %s",
                (item['PRD_ID'],)
            )
            result = cursor.fetchone()
            if result['stock_quantity'] < 0:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient stock for {item['NAME']}"
                )
        
        conn.commit()
        
        return {
            'transaction_id': transaction_id,
            'total_amount': total_amount,
            'change_amount': change_amount,
            'payment_method': payment.payment_method,
            'items': items
        }
        
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/sales/{transaction_id}/cancel")
def cancel_sale(transaction_id: int):
    """売上をキャンセル(返品処理)"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # トランザクション存在確認
        cursor.execute(
            "SELECT * FROM sales_transactions WHERE transaction_id = %s",
            (transaction_id,)
        )
        transaction = cursor.fetchone()
        
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        if transaction['is_cancelled']:
            raise HTTPException(status_code=400, detail="Transaction already cancelled")
        
        if transaction['is_pending']:
            raise HTTPException(status_code=400, detail="Cannot cancel pending transaction")
        
        # 売上明細取得
        cursor.execute(
            "SELECT * FROM sales_details WHERE transaction_id = %s",
            (transaction_id,)
        )
        details = cursor.fetchall()
        
        # 在庫を戻す
        for detail in details:
            update_stock = """
                UPDATE store_products 
                SET stock_quantity = stock_quantity + %s 
                WHERE PRD_ID = %s
            """
            cursor.execute(update_stock, (detail['quantity'], detail['PRD_ID']))
        
        # トランザクションをキャンセル済みに更新
        cursor.execute(
            """UPDATE sales_transactions 
               SET is_cancelled = TRUE, cancelled_at = NOW() 
               WHERE transaction_id = %s""",
            (transaction_id,)
        )
        
        conn.commit()
        
        return {"message": "Sale cancelled successfully", "transaction_id": transaction_id}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/sales/history")
def get_sales_history(days: int = 7):
    """売上履歴取得(最大60日)"""
    if days > 60:
        days = 60
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = """
            SELECT t.*, 
                   GROUP_CONCAT(
                       CONCAT(d.NAME, ' x', d.quantity) 
                       SEPARATOR ', '
                   ) as items_summary
            FROM sales_transactions t
            LEFT JOIN sales_details d ON t.transaction_id = d.transaction_id
            WHERE t.transaction_date >= DATE_SUB(NOW(), INTERVAL %s DAY)
                AND t.is_pending = FALSE
            GROUP BY t.transaction_id
            ORDER BY t.transaction_date DESC
        """
        cursor.execute(query, (days,))
        transactions = cursor.fetchall()
        
        return {"transactions": transactions, "count": len(transactions)}
        
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/qrcode/cancel/{transaction_id}")
def cancel_pending_transaction(transaction_id: int):
    """仮トランザクションをキャンセル(QRコード生成後に会計しなかった場合)"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # 仮トランザクションを削除
        cursor.execute(
            "DELETE FROM sales_transactions WHERE transaction_id = %s AND is_pending = TRUE",
            (transaction_id,)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pending transaction not found")
        
        conn.commit()
        
        return {"message": "Pending transaction cancelled"}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)