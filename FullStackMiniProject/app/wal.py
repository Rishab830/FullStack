import json
import os
import threading
from datetime import datetime
from typing import Dict, Any
import fcntl

class WriteAheadLog:
    def __init__(self, log_file='wal.log', checkpoint_file='checkpoint.log'):
        self.log_file = log_file
        self.checkpoint_file = checkpoint_file
        self.lock = threading.Lock()
        
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(log_file) or '.'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
    
    def write_log(self, operation: str, data: Dict[str, Any], transaction_id: str = None) -> int:
        """
        Write operation to log file before executing on database.
        Returns: Log Sequence Number (LSN)
        """
        with self.lock:
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'transaction_id': transaction_id or self._generate_txn_id(),
                'operation': operation,
                'data': data,
                'status': 'PENDING'
            }
            
            # Write to log file with file locking for crash safety
            with open(self.log_file, 'a') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(json.dumps(log_entry) + '\n')
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            return self._get_current_lsn()
    
    def commit_transaction(self, transaction_id: str):
        """Mark transaction as committed in log."""
        commit_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'transaction_id': transaction_id,
            'operation': 'COMMIT',
            'status': 'COMMITTED'
        }
        
        with open(self.log_file, 'a') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(commit_entry) + '\n')
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    def abort_transaction(self, transaction_id: str):
        """Mark transaction as aborted for rollback."""
        abort_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'transaction_id': transaction_id,
            'operation': 'ABORT',
            'status': 'ABORTED'
        }
        
        with open(self.log_file, 'a') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(abort_entry) + '\n')
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    def create_checkpoint(self, active_transactions: list):
        """Create checkpoint to limit recovery scan."""
        checkpoint_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'lsn': self._get_current_lsn(),
            'active_transactions': active_transactions
        }
        
        with open(self.checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
            f.flush()
            os.fsync(f.fileno())
    
    def recover(self, db):
        """
        Recover from crash by replaying log.
        Uses ARIES-style recovery: Analysis -> Redo -> Undo
        """
        if not os.path.exists(self.log_file):
            print("No WAL file found. Nothing to recover.")
            return
        
        print("Starting crash recovery...")
        
        # Phase 1: Analysis - identify committed and uncommitted transactions
        committed_txns = set()
        aborted_txns = set()
        pending_txns = {}
        
        with open(self.log_file, 'r') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    txn_id = entry.get('transaction_id')
                    
                    if entry['operation'] == 'COMMIT':
                        committed_txns.add(txn_id)
                    elif entry['operation'] == 'ABORT':
                        aborted_txns.add(txn_id)
                    elif entry['status'] == 'PENDING':
                        if txn_id not in pending_txns:
                            pending_txns[txn_id] = []
                        pending_txns[txn_id].append(entry)
        
        # Phase 2: Redo - replay committed transactions
        print(f"Redoing {len(committed_txns)} committed transactions...")
        for txn_id in committed_txns:
            if txn_id in pending_txns:
                for entry in pending_txns[txn_id]:
                    self._redo_operation(entry, db)
        
        # Phase 3: Undo - rollback uncommitted transactions
        uncommitted = set(pending_txns.keys()) - committed_txns - aborted_txns
        print(f"Undoing {len(uncommitted)} uncommitted transactions...")
        for txn_id in uncommitted:
            for entry in reversed(pending_txns[txn_id]):
                self._undo_operation(entry, db)
        
        # Archive old log and start fresh
        self._archive_log()
        print("Recovery complete!")
    
    def _redo_operation(self, entry: Dict, db):
        """Replay operation on database."""
        operation = entry['operation']
        data = entry['data']
        
        try:
            if operation == 'CREATE_PRODUCT':
                # Check if already exists to avoid duplicates
                existing = db.Products.find_one({'product_id': data['product_id']})
                if not existing:
                    db.Products.insert_one(data)
                    print(f"  Redone: CREATE_PRODUCT {data['product_id']}")
            
            elif operation == 'PLACE_BID':
                # Verify bid doesn't already exist
                existing_bid = db.Bids.find_one({
                    'product_id': data['product_id'],
                    'user_id': data['user_id'],
                    'amount': data['amount'],
                    'timestamp': data['timestamp']
                })
                if not existing_bid:
                    db.Bids.insert_one(data)
                    # Update product current price
                    db.Products.update_one(
                        {'product_id': data['product_id']},
                        {'$set': {'price': data['amount']}}
                    )
                    print(f"  Redone: PLACE_BID on product {data['product_id']}")
            
            elif operation == 'UPDATE_PRODUCT':
                db.Products.update_one(
                    {'product_id': data['product_id']},
                    {'$set': data['updates']}
                )
                print(f"  Redone: UPDATE_PRODUCT {data['product_id']}")
            
            elif operation == 'DELETE_PRODUCT':
                db.Products.delete_one({'product_id': data['product_id']})
                print(f"  Redone: DELETE_PRODUCT {data['product_id']}")
                
        except Exception as e:
            print(f"  Error redoing {operation}: {e}")
    
    def _undo_operation(self, entry: Dict, db):
        """Rollback operation (compensation)."""
        operation = entry['operation']
        data = entry['data']
        
        try:
            if operation == 'CREATE_PRODUCT':
                db.Products.delete_one({'product_id': data['product_id']})
                print(f"  Undone: CREATE_PRODUCT {data['product_id']}")
            
            elif operation == 'PLACE_BID':
                # Remove the bid
                db.Bids.delete_one({
                    'product_id': data['product_id'],
                    'user_id': data['user_id'],
                    'amount': data['amount']
                })
                # Restore previous price from bid history
                prev_bid = db.Bids.find_one(
                    {'product_id': data['product_id']},
                    sort=[('timestamp', -1)]
                )
                if prev_bid:
                    db.Products.update_one(
                        {'product_id': data['product_id']},
                        {'$set': {'price': prev_bid['amount']}}
                    )
                else:
                    # Restore to starting price
                    product = db.Products.find_one({'product_id': data['product_id']})
                    if product and 'starting_price' in product:
                        db.Products.update_one(
                            {'product_id': data['product_id']},
                            {'$set': {'price': product['starting_price']}}
                        )
                print(f"  Undone: PLACE_BID on product {data['product_id']}")
            
            elif operation == 'UPDATE_PRODUCT':
                if 'old_values' in data:
                    db.Products.update_one(
                        {'product_id': data['product_id']},
                        {'$set': data['old_values']}
                    )
                    print(f"  Undone: UPDATE_PRODUCT {data['product_id']}")
                    
        except Exception as e:
            print(f"  Error undoing {operation}: {e}")
    
    def _generate_txn_id(self) -> str:
        """Generate unique transaction ID."""
        return f"TXN-{datetime.utcnow().timestamp()}-{os.getpid()}"
    
    def _get_current_lsn(self) -> int:
        """Get current log sequence number (line count)."""
        if not os.path.exists(self.log_file):
            return 0
        with open(self.log_file, 'r') as f:
            return sum(1 for _ in f)
    
    def _archive_log(self):
        """Archive old log after successful recovery."""
        if os.path.exists(self.log_file):
            archive_name = f"{self.log_file}.{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.recovered"
            os.rename(self.log_file, archive_name)
            print(f"Archived log to {archive_name}")
