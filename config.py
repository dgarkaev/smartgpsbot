#Redis
redis_host='app-server'
redis_port=6379
redis_db = 0
redis_url=f'redis://{redis_host}:{redis_port}/{redis_db}'

#
redis_key='SmartGPSTracker'

import os
ENVIRONMENT = os.getenv('ENVIRONMENT')
print(ENVIRONMENT)
if ENVIRONMENT:
    #test
    API_TOKEN = '0000000000:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
else:
    #prod
    API_TOKEN = '1111111111:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'