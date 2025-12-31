import json
import os
from datetime import datetime
from threading import Lock
from enum import Enum
from bson import Binary, ObjectId

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime, Binary, and ObjectId objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return {
                '__type__': 'datetime',
                'value': obj.isoformat()
            }
        elif isinstance(obj, Binary):
            return {
                '__type__': 'binary',
                'value': 'BINARY_DATA'  # Don't serialize actual binary data
            }
        elif isinstance(obj, ObjectId):
            return {
                '__type__': 'objectid',
                'value': str(obj)
            }
        return super().default(obj)

def datetime_decoder(dct):
    """Custom JSON decoder that reconstructs datetime objects"""
    if '__type__' in dct:
        if dct['__type__'] == 'datetime':
            return datetime.fromisoformat(dct['value'])
        elif dct['__type__'] == 'binary':
            return None  # Binary data not stored in logs
        elif dct['__type__'] == 'objectid':
            return ObjectId(dct['value'])
    return dct

class OperationType(Enum):
    """Define types of operations that can be logged"""
    BID = "BID"
    CREATE_PRODUCT = "CREATE_PRODUCT"
    UPDATE_PRODUCT = "UPDATE_PRODUCT"
    DELETE_PRODUCT = "DELETE_PRODUCT"
    END_AUCTION = "END_AUCTION"
    CREATE_USER = "CREATE_USER"
    UPDATE_USER = "UPDATE_USER"
    DELETE_USER = "DELETE_USER"

class TransactionStatus(Enum):
    """Define transaction statuses"""
    BEGIN = "BEGIN"
    COMMIT = "COMMIT"
    ABORT = "ABORT"

class WALManager:
    """
    Write-Ahead Logging Manager for auction system
    Ensures atomicity and durability of critical operations
    """

    def __init__(self, wal_dir="wal_logs", checkpoint_interval=100):
        self.wal_dir = wal_dir
        self.checkpoint_interval = checkpoint_interval
        self.lock = Lock()
        self.transaction_counter = 0
        self.current_log_file = None
        self.log_entry_count = 0

        # Create WAL directory if it doesn't exist
        if not os.path.exists(self.wal_dir):
            os.makedirs(self.wal_dir)

        # Initialize current log file
        self._initialize_log_file()

    def _initialize_log_file(self):
        """Initialize or rotate log file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_file = os.path.join(
            self.wal_dir, 
            f"wal_{timestamp}.log"
        )

    def _get_transaction_id(self):
        """Generate unique transaction ID"""
        with self.lock:
            self.transaction_counter += 1
            return f"TXN_{self.transaction_counter}_{datetime.now().timestamp()}"

    def _serialize_for_log(self, data):
        """Serialize data with custom encoder"""
        return json.dumps(data, cls=DateTimeEncoder)

    def _deserialize_from_log(self, json_str):
        """Deserialize data with custom decoder"""
        return json.loads(json_str, object_hook=datetime_decoder)

    def begin_transaction(self, operation_type, user_id=None):
        """
        Start a new transaction
        Returns transaction ID
        """
        txn_id = self._get_transaction_id()

        log_entry = {
            "txn_id": txn_id,
            "status": TransactionStatus.BEGIN.value,
            "operation_type": operation_type.value,
            "timestamp": datetime.now().isoformat(),  # Store as ISO string
            "user_id": user_id,
            "data": {}
        }

        self._write_log(log_entry)
        return txn_id

    def log_operation(self, txn_id, operation_type, old_state, new_state, metadata=None):
        """
        Log operation details with old and new states for recovery

        Args:
            txn_id: Transaction ID
            operation_type: Type of operation (OperationType enum)
            old_state: Previous state before operation
            new_state: New state after operation
            metadata: Additional metadata (e.g., product_id, user_id)
        """
        log_entry = {
            "txn_id": txn_id,
            "status": "EXECUTING",
            "operation_type": operation_type.value,
            "timestamp": datetime.now().isoformat(),  # Store as ISO string
            "old_state": old_state,
            "new_state": new_state,
            "metadata": metadata or {}
        }

        self._write_log(log_entry)

    def commit_transaction(self, txn_id):
        """Mark transaction as committed"""
        log_entry = {
            "txn_id": txn_id,
            "status": TransactionStatus.COMMIT.value,
            "timestamp": datetime.now().isoformat()  # Store as ISO string
        }

        self._write_log(log_entry)
        self._flush_log()

    def abort_transaction(self, txn_id, reason=None):
        """Mark transaction as aborted"""
        log_entry = {
            "txn_id": txn_id,
            "status": TransactionStatus.ABORT.value,
            "timestamp": datetime.now().isoformat(),  # Store as ISO string
            "reason": reason
        }

        self._write_log(log_entry)
        self._flush_log()

    def _write_log(self, log_entry):
        """Write log entry to file with proper serialization"""
        with self.lock:
            try:
                with open(self.current_log_file, 'a') as f:
                    # Use custom serializer
                    json_str = self._serialize_for_log(log_entry)
                    f.write(json_str + '\n')

                self.log_entry_count += 1

                # Check if checkpoint is needed
                if self.log_entry_count >= self.checkpoint_interval:
                    self._checkpoint()
            except Exception as e:
                print(f"Error writing to WAL: {e}")
                raise

    def _flush_log(self):
        """Force flush log to disk"""
        with self.lock:
            # Ensure data is written to disk
            if os.path.exists(self.current_log_file):
                try:
                    with open(self.current_log_file, 'a') as f:
                        f.flush()
                        os.fsync(f.fileno())
                except Exception as e:
                    print(f"Error flushing WAL: {e}")

    def _checkpoint(self):
        """Create checkpoint and archive old logs"""
        checkpoint_file = os.path.join(
            self.wal_dir,
            f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        checkpoint_data = {
            "timestamp": datetime.now().isoformat(),
            "log_file": self.current_log_file,
            "entry_count": self.log_entry_count
        }

        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)

        # Reset counter and rotate log file
        self.log_entry_count = 0
        self._initialize_log_file()

    def recover(self, db):
        """
        Recover from crash by replaying WAL

        Args:
            db: MongoDB database instance
        """
        print("Starting WAL recovery...")

        # Get all log files sorted by timestamp
        log_files = sorted([
            f for f in os.listdir(self.wal_dir) 
            if f.startswith('wal_') and f.endswith('.log')
        ])

        if not log_files:
            print("No WAL files found. Nothing to recover.")
            return

        transactions = {}

        # Read all log entries
        for log_file in log_files:
            log_path = os.path.join(self.wal_dir, log_file)
            with open(log_path, 'r') as f:
                for line in f:
                    try:
                        # Use custom deserializer
                        entry = self._deserialize_from_log(line.strip())
                        txn_id = entry['txn_id']

                        if txn_id not in transactions:
                            transactions[txn_id] = []

                        transactions[txn_id].append(entry)
                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"Skipping malformed log entry: {str(e)}")

        # Process transactions
        for txn_id, entries in transactions.items():
            self._recover_transaction(txn_id, entries, db)

        print(f"Recovery complete. Processed {len(transactions)} transactions.")

    def _recover_transaction(self, txn_id, entries, db):
        """
        Recover a single transaction

        Args:
            txn_id: Transaction ID
            entries: List of log entries for this transaction
            db: MongoDB database instance
        """
        # Check if transaction was committed
        statuses = [e['status'] for e in entries]

        if TransactionStatus.COMMIT.value in statuses:
            # Transaction was committed, ensure it's applied
            print(f"Transaction {txn_id} was committed. Verifying...")
            self._verify_transaction(entries, db)

        elif TransactionStatus.ABORT.value in statuses:
            # Transaction was aborted, rollback if needed
            print(f"Transaction {txn_id} was aborted. Rolling back...")
            self._rollback_transaction(entries, db)

        else:
            # Transaction incomplete (crash during execution), rollback
            print(f"Transaction {txn_id} incomplete. Rolling back...")
            self._rollback_transaction(entries, db)

    def _verify_transaction(self, entries, db):
        """Verify committed transaction was applied"""
        for entry in entries:
            if entry['status'] == 'EXECUTING':
                op_type = entry['operation_type']
                new_state = entry.get('new_state', {})
                metadata = entry.get('metadata', {})

                # Verify the new state exists in database
                if op_type == OperationType.BID.value:
                    product_id = metadata.get('product_id')
                    product = db.Products.find_one({'product_id': product_id})

                    if product and product.get('price') != new_state.get('price'):
                        print(f"Reapplying bid for product {product_id}")
                        self._apply_bid(new_state, metadata, db)

    def _rollback_transaction(self, entries, db):
        """Rollback incomplete or aborted transaction"""
        for entry in reversed(entries):
            if entry['status'] == 'EXECUTING':
                op_type = entry['operation_type']
                old_state = entry.get('old_state', {})
                metadata = entry.get('metadata', {})

                # Restore old state
                if op_type == OperationType.BID.value:
                    product_id = metadata.get('product_id')
                    print(f"Rolling back bid for product {product_id}")

                    if old_state:
                        db.Products.update_one(
                            {'product_id': product_id},
                            {'$set': {'price': old_state.get('price')}}
                        )

                        # Remove last history entry if it was added
                        db.Products.update_one(
                            {'product_id': product_id},
                            {'$pop': {'history': 1}}
                        )

    def _apply_bid(self, new_state, metadata, db):
        """Reapply bid operation during recovery"""
        product_id = metadata.get('product_id')

        db.Products.update_one(
            {'product_id': product_id},
            {'$set': {'price': new_state.get('price')}}
        )

        if 'history_entry' in new_state:
            db.Products.update_one(
                {'product_id': product_id},
                {'$push': {'history': new_state['history_entry']}}
            )

    def cleanup_old_logs(self, days=7):
        """
        Clean up old log files

        Args:
            days: Number of days to keep logs
        """
        cutoff_time = datetime.now().timestamp() - (days * 86400)

        for filename in os.listdir(self.wal_dir):
            filepath = os.path.join(self.wal_dir, filename)
            if os.path.getmtime(filepath) < cutoff_time:
                os.remove(filepath)
                print(f"Removed old log file: {filename}")
