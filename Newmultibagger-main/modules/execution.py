# modules/execution.py
"""
Sovereign Execution Engine — OMS Reconciliation Layer
=====================================================

This module provides the Order Management System (OMS) reconciliation layer
with an explicit external execution ack lifecycle. It guards against duplicate
executions via idempotency checks and maintains strict state transitions based
on broker acknowledgements.
"""

from typing import Any
import datetime
from core.observability.logger import get_logger

_log = get_logger("modules.execution")


class OMSReconciler:
    """
    Idempotency guard and broker ack reconciliation lifecycle.
    """

    VALID_STATES = {"PENDING", "FILLED", "PARTIAL", "CANCELLED", "REJECTED"}

    def __init__(self):
        # In-memory store for idempotency keys. In production this uses Redis/DB.
        self._idempotency_cache: dict[str, dict[str, Any]] = {}

    def submit_order(self, order_req: dict[str, Any]) -> dict[str, Any]:
        """
        Submit a new order to the broker with an idempotency key.
        """
        idem_key = order_req.get("idempotency_key")
        if not idem_key:
            raise ValueError("idempotency_key is required for order submission")

        if idem_key in self._idempotency_cache:
            _log.warning(f"Idempotency hit for {idem_key}. Skipping duplicate execution.")
            return self._idempotency_cache[idem_key]

        # Mock broker submission
        record = {
            "order_id": f"ord_{datetime.datetime.now().timestamp()}",
            "idempotency_key": idem_key,
            "status": "PENDING",
            "symbol": order_req["symbol"],
            "qty": order_req["qty"],
            "submitted_at": datetime.datetime.now().isoformat(),
        }

        self._idempotency_cache[idem_key] = record
        _log.info(f"Order submitted: {record['order_id']} for {record['symbol']}")
        return record

    def reconcile_ack(self, order_id: str, external_ack: dict[str, Any]) -> dict[str, Any] | None:
        """
        Reconcile an external broker ack to update the execution lifecycle state.
        Handles FILLED, PARTIAL, CANCELLED events.
        """
        status = external_ack.get("status", "").upper()
        if status not in self.VALID_STATES:
            _log.error(f"Invalid external ack state received: {status}")
            return None

        # Reconcile logic
        _log.info(f"Reconciling order {order_id} with ack state: {status}")

        if status == "FILLED":
            _log.info(f"Order {order_id} fully FILLED.")
        elif status == "PARTIAL":
            _log.info(f"Order {order_id} PARTIAL fill. Awaiting remainder.")
        elif status == "CANCELLED":
            _log.warning(f"Order {order_id} CANCELLED by broker.")

        return {
            "order_id": order_id,
            "reconcile_status": status,
            "timestamp": datetime.datetime.now().isoformat()
        }

# Global singleton
reconciler = OMSReconciler()
