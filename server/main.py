from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, tasks

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

# Fixed per-warehouse shipping lead time for restocking orders
WAREHOUSE_LEAD_TIME_DAYS = {
    "San Francisco": 3,
    "Tokyo": 10,
    "London": 7
}
DEFAULT_LEAD_TIME_DAYS = 7

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None
    lead_time_days: Optional[int] = None
    source: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    warehouse: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class Task(BaseModel):
    id: str
    title: str
    priority: str
    dueDate: str
    status: str = "pending"

class CreateTaskRequest(BaseModel):
    title: str
    priority: str
    dueDate: str

class RestockRecommendation(BaseModel):
    item_sku: str
    item_name: str
    warehouse: str
    current_demand: int
    forecasted_demand: int
    demand_gap: int
    trend: str
    unit_cost: float
    recommended_quantity: int
    estimated_cost: float
    lead_time_days: int
    fully_funded: bool

class RestockRecommendationResponse(BaseModel):
    budget: float
    total_estimated_cost: float
    remaining_budget: float
    warehouse_filter: Optional[str] = None
    items: List[RestockRecommendation]

class RestockOrderLineItem(BaseModel):
    sku: str
    name: str
    quantity: int
    unit_price: float

class CreateRestockOrderRequest(BaseModel):
    budget: float
    warehouse: Optional[str] = None
    items: List[RestockOrderLineItem]

class RestockOrderResponse(BaseModel):
    order: Order

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/restocking/recommendations", response_model=RestockRecommendationResponse)
def get_restocking_recommendations(
    budget: float,
    warehouse: Optional[str] = None
):
    """Recommend items to restock from the demand forecast within a given budget"""
    if budget < 0:
        raise HTTPException(status_code=400, detail="Budget must be non-negative")

    candidates = [f for f in demand_forecasts if f.get('trend') == 'increasing']

    if warehouse and warehouse != 'all':
        candidates = [f for f in candidates if f.get('warehouse') == warehouse]

    candidates = [
        {**f, 'demand_gap': f['forecasted_demand'] - f['current_demand']}
        for f in candidates
    ]
    candidates = [f for f in candidates if f['demand_gap'] > 0]
    candidates.sort(key=lambda f: (f['demand_gap'], f['unit_cost']), reverse=True)

    remaining = budget
    result = []
    for item in candidates:
        max_affordable_qty = int(remaining // item['unit_cost']) if item['unit_cost'] > 0 else 0
        recommended_quantity = min(item['demand_gap'], max_affordable_qty)

        if recommended_quantity <= 0:
            continue

        estimated_cost = round(recommended_quantity * item['unit_cost'], 2)
        remaining = round(remaining - estimated_cost, 2)

        result.append(RestockRecommendation(
            item_sku=item['item_sku'],
            item_name=item['item_name'],
            warehouse=item['warehouse'],
            current_demand=item['current_demand'],
            forecasted_demand=item['forecasted_demand'],
            demand_gap=item['demand_gap'],
            trend=item['trend'],
            unit_cost=item['unit_cost'],
            recommended_quantity=recommended_quantity,
            estimated_cost=estimated_cost,
            lead_time_days=WAREHOUSE_LEAD_TIME_DAYS.get(item['warehouse'], DEFAULT_LEAD_TIME_DAYS),
            fully_funded=(recommended_quantity == item['demand_gap'])
        ))

    total_estimated_cost = round(sum(r.estimated_cost for r in result), 2)

    return RestockRecommendationResponse(
        budget=budget,
        total_estimated_cost=total_estimated_cost,
        remaining_budget=round(budget - total_estimated_cost, 2),
        warehouse_filter=warehouse,
        items=result
    )

@app.post("/api/restocking/orders", response_model=RestockOrderResponse, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a combined restocking order built from accepted recommendations"""
    if not request.items:
        raise HTTPException(status_code=400, detail="No items to order")

    total_value = sum(item.quantity * item.unit_price for item in request.items)
    if total_value > request.budget + 0.01:
        raise HTTPException(status_code=400, detail="Order total exceeds budget")

    if request.warehouse and request.warehouse != 'all':
        order_warehouse = request.warehouse
        lead_time_days = WAREHOUSE_LEAD_TIME_DAYS.get(order_warehouse, DEFAULT_LEAD_TIME_DAYS)
    else:
        item_warehouses = set()
        for line_item in request.items:
            forecast = next((f for f in demand_forecasts if f['item_sku'] == line_item.sku), None)
            if forecast:
                item_warehouses.add(forecast['warehouse'])

        if len(item_warehouses) == 1:
            order_warehouse = next(iter(item_warehouses))
            lead_time_days = WAREHOUSE_LEAD_TIME_DAYS.get(order_warehouse, DEFAULT_LEAD_TIME_DAYS)
        elif len(item_warehouses) > 1:
            order_warehouse = None
            lead_time_days = max(
                WAREHOUSE_LEAD_TIME_DAYS.get(w, DEFAULT_LEAD_TIME_DAYS) for w in item_warehouses
            )
        else:
            order_warehouse = None
            lead_time_days = DEFAULT_LEAD_TIME_DAYS

    order_date = datetime.now()
    expected_delivery = order_date + timedelta(days=lead_time_days)

    existing_seqs = []
    for o in orders:
        try:
            existing_seqs.append(int(o['order_number'].split('-')[-1]))
        except (ValueError, KeyError, AttributeError):
            continue
    next_seq = (max(existing_seqs) + 1) if existing_seqs else (len(orders) + 1)
    order_number = f"ORD-2025-{next_seq:04d}"

    existing_ids = [int(o['id']) for o in orders if o.get('id', '').isdigit()]
    next_id = str((max(existing_ids) + 1) if existing_ids else (len(orders) + 1))

    new_order = {
        "id": next_id,
        "order_number": order_number,
        "customer": "Internal Restock Order",
        "items": [
            {"sku": item.sku, "name": item.name, "quantity": item.quantity, "unit_price": item.unit_price}
            for item in request.items
        ],
        "status": "Processing",
        "warehouse": order_warehouse,
        "category": None,
        "order_date": order_date.strftime("%Y-%m-%dT%H:%M:%S"),
        "expected_delivery": expected_delivery.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_value": round(total_value, 2),
        "actual_delivery": None,
        "lead_time_days": lead_time_days,
        "source": "restock"
    }

    orders.append(new_order)

    return RestockOrderResponse(order=new_order)

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.post("/api/purchase-orders", response_model=PurchaseOrder, status_code=201)
def create_purchase_order(request: CreatePurchaseOrderRequest):
    """Create a purchase order for a backlog item"""
    existing_ids = [int(po["id"].split("-")[-1]) for po in purchase_orders if po.get("id", "").split("-")[-1].isdigit()]
    next_seq = (max(existing_ids) + 1) if existing_ids else 1

    new_po = {
        "id": f"PO-{next_seq:04d}",
        "backlog_item_id": request.backlog_item_id,
        "supplier_name": request.supplier_name,
        "quantity": request.quantity,
        "unit_cost": request.unit_cost,
        "expected_delivery_date": request.expected_delivery_date,
        "status": "Ordered",
        "created_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "notes": request.notes
    }
    purchase_orders.append(new_po)
    return new_po

@app.get("/api/purchase-orders/{backlog_item_id}", response_model=PurchaseOrder)
def get_purchase_order_by_backlog_item(backlog_item_id: str):
    """Get the purchase order associated with a backlog item"""
    po = next((po for po in purchase_orders if po["backlog_item_id"] == backlog_item_id), None)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """Get all tasks"""
    return tasks

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(request: CreateTaskRequest):
    """Create a new task"""
    existing_ids = [int(t["id"].split("-")[-1]) for t in tasks if t.get("id", "").split("-")[-1].isdigit()]
    next_seq = (max(existing_ids) + 1) if existing_ids else 1

    new_task = {
        "id": f"TASK-{next_seq:04d}",
        "title": request.title,
        "priority": request.priority,
        "dueDate": request.dueDate,
        "status": "pending"
    }
    tasks.append(new_task)
    return new_task

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task"""
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.remove(task)
    return {"message": "Task deleted"}

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: str):
    """Toggle a task's completion status"""
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["status"] = "completed" if task["status"] == "pending" else "pending"
    return task

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
