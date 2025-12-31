# Distributed Deployment Guide

## Prerequisites

### 1. MongoDB Replica Set Setup

MongoDB transactions require a replica set (not standalone MongoDB).

#### Local Development (Docker Compose)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mongodb-primary:
    image: mongo:6.0
    container_name: mongodb-primary
    command: mongod --replSet rs0 --port 27017
    ports:
      - "27017:27017"
    volumes:
      - mongo-data-1:/data/db
    networks:
      - auction-network

  mongodb-secondary:
    image: mongo:6.0
    container_name: mongodb-secondary
    command: mongod --replSet rs0 --port 27018
    ports:
      - "27018:27018"
    volumes:
      - mongo-data-2:/data/db
    networks:
      - auction-network

  mongodb-arbiter:
    image: mongo:6.0
    container_name: mongodb-arbiter
    command: mongod --replSet rs0 --port 27019
    ports:
      - "27019:27019"
    volumes:
      - mongo-data-3:/data/db
    networks:
      - auction-network

  redis:
    image: redis:7-alpine
    container_name: redis
    ports:
      - "6379:6379"
    networks:
      - auction-network

  flask-instance-1:
    build: .
    container_name: flask-instance-1
    environment:
      - INSTANCE_ID=instance-1
      - PORT=5001
      - MONGODB_URI=mongodb://mongodb-primary:27017,mongodb-secondary:27018/?replicaSet=rs0
      - REDIS_URL=redis://redis:6379
    ports:
      - "5001:5001"
    depends_on:
      - mongodb-primary
      - mongodb-secondary
      - mongodb-arbiter
      - redis
    networks:
      - auction-network

  flask-instance-2:
    build: .
    container_name: flask-instance-2
    environment:
      - INSTANCE_ID=instance-2
      - PORT=5002
      - MONGODB_URI=mongodb://mongodb-primary:27017,mongodb-secondary:27018/?replicaSet=rs0
      - REDIS_URL=redis://redis:6379
    ports:
      - "5002:5002"
    depends_on:
      - mongodb-primary
      - mongodb-secondary
      - mongodb-arbiter
      - redis
    networks:
      - auction-network

  flask-instance-3:
    build: .
    container_name: flask-instance-3
    environment:
      - INSTANCE_ID=instance-3
      - PORT=5003
      - MONGODB_URI=mongodb://mongodb-primary:27017,mongodb-secondary:27018/?replicaSet=rs0
      - REDIS_URL=redis://redis:6379
    ports:
      - "5003:5003"
    depends_on:
      - mongodb-primary
      - mongodb-secondary
      - mongodb-arbiter
      - redis
    networks:
      - auction-network

  nginx:
    image: nginx:alpine
    container_name: nginx-lb
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - flask-instance-1
      - flask-instance-2
      - flask-instance-3
    networks:
      - auction-network

volumes:
  mongo-data-1:
  mongo-data-2:
  mongo-data-3:

networks:
  auction-network:
    driver: bridge
```

#### Initialize Replica Set

After starting containers:

```bash
# Start all containers
docker-compose up -d

# Initialize replica set
docker exec -it mongodb-primary mongosh --eval "
rs.initiate({
  _id: 'rs0',
  members: [
    { _id: 0, host: 'mongodb-primary:27017', priority: 2 },
    { _id: 1, host: 'mongodb-secondary:27018', priority: 1 },
    { _id: 2, host: 'mongodb-arbiter:27019', arbiterOnly: true }
  ]
})
"

# Check replica set status
docker exec -it mongodb-primary mongosh --eval "rs.status()"
```

### 2. Nginx Load Balancer Configuration

Create `nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream flask_backend {
        # Round-robin load balancing
        least_conn;  # Use least connections algorithm

        server flask-instance-1:5001 max_fails=3 fail_timeout=30s;
        server flask-instance-2:5002 max_fails=3 fail_timeout=30s;
        server flask-instance-3:5003 max_fails=3 fail_timeout=30s;
    }

    # Enable sticky sessions (optional, for better user experience)
    # Requires nginx-sticky-module-ng
    # sticky cookie srv_id expires=1h domain=.example.com path=/;

    server {
        listen 80;
        server_name localhost;

        # Increase timeout for long-running requests
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # Buffer settings
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;

        location / {
            proxy_pass http://flask_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Health check response
            proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
        }

        # Health check endpoint
        location /health {
            access_log off;
            proxy_pass http://flask_backend/health;
        }

        # Static files (if any)
        location /static {
            alias /app/static;
            expires 30d;
        }
    }
}
```

### 3. Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (will be overridden by environment variable)
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:' + __import__('os').getenv('PORT', '5000') + '/health')"

# Run application
CMD ["python", "app_distributed_mongodb_transactions.py"]
```

### 4. Updated requirements.txt

```txt
Flask==3.0.0
pymongo==4.6.0
Flask-Session==0.5.0
redis==5.0.1
python-dateutil==2.8.2
gunicorn==21.2.0
```

### 5. Add Health Check Endpoint

Add to your Flask app:

```python
@app.route('/health')
def health():
    """Health check endpoint for load balancer"""
    try:
        # Check MongoDB connection
        client.admin.command('ping')

        # Check Redis connection
        from redis import Redis
        redis_client = Redis.from_url(app.config["SESSION_REDIS"])
        redis_client.ping()

        return {'status': 'healthy', 'instance': INSTANCE_ID}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e), 'instance': INSTANCE_ID}, 500
```

## Deployment Steps

### Local Development

```bash
# 1. Start infrastructure
docker-compose up -d mongodb-primary mongodb-secondary mongodb-arbiter redis

# 2. Initialize replica set (wait 30 seconds first)
sleep 30
docker exec -it mongodb-primary mongosh --eval "rs.initiate(...)"

# 3. Start Flask instances
docker-compose up -d flask-instance-1 flask-instance-2 flask-instance-3

# 4. Start nginx
docker-compose up -d nginx

# 5. Access application
curl http://localhost/
```

### Production (AWS/GCP/Azure)

#### Option 1: AWS Elastic Beanstalk Multi-Container

Create `.ebextensions/load-balancer.config`:

```yaml
option_settings:
  aws:elasticbeanstalk:environment:
    LoadBalancerType: application
  aws:elasticbeanstalk:environment:process:default:
    HealthCheckPath: /health
    HealthCheckInterval: 30
    HealthCheckTimeout: 10
    HealthyThresholdCount: 2
    UnhealthyThresholdCount: 5
```

#### Option 2: Kubernetes Deployment

Create `kubernetes-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auction-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: auction
  template:
    metadata:
      labels:
        app: auction
    spec:
      containers:
      - name: flask-app
        image: your-registry/auction-app:latest
        ports:
        - containerPort: 5000
        env:
        - name: INSTANCE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: MONGODB_URI
          valueFrom:
            secretKeyRef:
              name: mongodb-secret
              key: uri
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: auction-service
spec:
  type: LoadBalancer
  selector:
    app: auction
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5000
```

#### Option 3: Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml auction-stack

# Scale services
docker service scale auction-stack_flask-app=5
```

## Configuration Management

### Environment Variables

Create `.env` file (don't commit to git):

```bash
# MongoDB Configuration
MONGODB_URI=mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0
MONGODB_DATABASE=BidHub

# Redis Configuration
REDIS_URL=redis://redis-server:6379/0

# Flask Configuration
FLASK_ENV=production
SECRET_KEY=your-super-secret-key-change-this

# Instance Configuration
INSTANCE_ID=auto  # Will use container hostname if set to 'auto'
PORT=5000

# Session Configuration
SESSION_TYPE=redis
SESSION_PERMANENT=False
SESSION_USE_SIGNER=True
SESSION_KEY_PREFIX=auction:

# Security
SECURE_COOKIES=True
SECURE_HEADERS=True
```

### Load Environment in Flask

Update your app:

```python
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB setup
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/?replicaSet=rs0')
client = MongoClient(MONGODB_URI)

# Redis setup
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
app.config["SESSION_REDIS"] = REDIS_URL

# Instance ID
INSTANCE_ID = os.getenv('INSTANCE_ID', 'auto')
if INSTANCE_ID == 'auto':
    import socket
    INSTANCE_ID = socket.gethostname()
```

## Monitoring and Logging

### Centralized Logging with ELK Stack

Add to `docker-compose.yml`:

```yaml
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    networks:
      - auction-network

  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    ports:
      - "5044:5044"
    depends_on:
      - elasticsearch
    networks:
      - auction-network

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    ports:
      - "5601:5601"
    depends_on:
      - elasticsearch
    networks:
      - auction-network
```

### Application Metrics with Prometheus

Add to Flask app:

```python
from prometheus_flask_exporter import PrometheusMetrics

metrics = PrometheusMetrics(app)

# Custom metrics
bid_counter = metrics.counter(
    'bids_total', 'Total number of bids',
    labels={'instance': lambda: INSTANCE_ID}
)

@app.route('/bid', methods=['POST'])
def bid():
    bid_counter.inc()  # Increment counter
    # ... rest of bid logic
```

## Testing Distributed Setup

### Test Script

Create `test_distributed.py`:

```python
import requests
import concurrent.futures
import time

BASE_URL = "http://localhost"

def test_concurrent_bids():
    """Test race condition prevention"""
    product_id = 1

    def place_bid(user_id, amount):
        try:
            response = requests.post(
                f"{BASE_URL}/bid?product_id={product_id}",
                data={'bidAmount': amount},
                cookies={'user_id': str(user_id)}
            )
            return response.status_code, amount
        except Exception as e:
            return None, str(e)

    # Simulate 10 concurrent bids
    bids = [(i, 100 + i) for i in range(1, 11)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda x: place_bid(*x), bids))

    print("Concurrent bid test results:")
    for i, (status, amount) in enumerate(results):
        print(f"  Bid {i+1}: Amount ${amount} - Status: {status}")

    # Verify only highest bid won
    # Check database...

def test_load_balancing():
    """Verify requests are distributed across instances"""
    instance_counts = {}

    for i in range(100):
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            instance_id = response.json().get('instance')
            instance_counts[instance_id] = instance_counts.get(instance_id, 0) + 1

    print("\nLoad balancing distribution:")
    for instance, count in instance_counts.items():
        print(f"  {instance}: {count} requests ({count}%)")

def test_failover():
    """Test instance failure handling"""
    print("\nTesting failover...")

    # Get initial health
    response = requests.get(f"{BASE_URL}/health")
    initial_instance = response.json().get('instance')
    print(f"Initial instance: {initial_instance}")

    # TODO: Simulate instance failure
    # docker stop flask-instance-1

    # Verify other instances handle requests
    time.sleep(2)
    response = requests.get(f"{BASE_URL}/health")
    new_instance = response.json().get('instance')
    print(f"After failover: {new_instance}")

    assert new_instance != initial_instance, "Failover did not occur"

if __name__ == '__main__':
    print("Testing distributed deployment...")
    test_concurrent_bids()
    test_load_balancing()
    # test_failover()  # Uncomment to test
```

Run tests:

```bash
python test_distributed.py
```

## Troubleshooting

### Common Issues

#### 1. Replica Set Not Initialized

**Symptom**: `MongoClient error: not master and slaveOk=false`

**Solution**:
```bash
docker exec -it mongodb-primary mongosh --eval "rs.status()"
# If not initialized, run rs.initiate() again
```

#### 2. Redis Connection Failed

**Symptom**: Flask sessions not working

**Solution**:
```bash
# Check Redis
docker exec -it redis redis-cli ping
# Should return: PONG

# Check Flask can connect
docker exec -it flask-instance-1 python -c "from redis import Redis; r = Redis.from_url('redis://redis:6379'); print(r.ping())"
```

#### 3. Transaction Aborted

**Symptom**: Bids fail with transaction error

**Solution**:
- Ensure MongoDB is in replica set mode
- Check MongoDB version (requires 4.0+)
- Verify all nodes are healthy: `rs.status()`

#### 4. Load Balancer Not Distributing

**Symptom**: All requests go to one instance

**Solution**:
- Check nginx logs: `docker logs nginx-lb`
- Verify all instances are healthy
- Check sticky session configuration

## Production Checklist

- [ ] MongoDB replica set with at least 3 nodes
- [ ] Redis persistence enabled (RDB + AOF)
- [ ] Load balancer health checks configured
- [ ] SSL/TLS certificates installed
- [ ] Session timeout configured
- [ ] Rate limiting implemented
- [ ] CORS configured properly
- [ ] Environment variables secured
- [ ] Monitoring and alerting set up
- [ ] Backup strategy implemented
- [ ] Disaster recovery plan documented
- [ ] Load testing completed
- [ ] Security audit performed

## Performance Tuning

### MongoDB Optimization

```javascript
// Create indexes for frequent queries
db.Products.createIndex({ "product_id": 1 }, { unique: true })
db.Products.createIndex({ "end_time": 1 })
db.Products.createIndex({ "user_id": 1 })
db.Users.createIndex({ "email": 1 }, { unique: true })
db.AuditLog.createIndex({ "timestamp": 1 })

// Set TTL index for audit logs (auto-delete after 90 days)
db.AuditLog.createIndex({ "timestamp": 1 }, { expireAfterSeconds: 7776000 })
```

### Connection Pooling

```python
# Configure MongoDB connection pool
client = MongoClient(
    MONGODB_URI,
    maxPoolSize=50,
    minPoolSize=10,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=10000
)
```

### Gunicorn Configuration

Create `gunicorn.conf.py`:

```python
import multiprocessing

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
preload_app = True
accesslog = "-"
errorlog = "-"
loglevel = "info"
```

Run with Gunicorn:

```bash
gunicorn -c gunicorn.conf.py app_distributed_mongodb_transactions:app
```
