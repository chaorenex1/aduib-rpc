import asyncio
import logging

from aduib_rpc.server.tasks.task_manager import TaskManagerConfig
from aduib_rpc.utils.constant import TransportSchemes
from aduib_rpc.app import run_serve

logging.basicConfig(level=logging.DEBUG)

async def main():
    registry_config = {
        "server_addresses": "10.0.0.96:8848",
        "namespace": "eeb6433f-d68c-4b3b-a4a7-eeff19110e4d",
        "group_name": "DEFAULT_GROUP",
        "username": "nacos",
        "password": "nacos11.",
        "max_retry": 3,
        "DISCOVERY_SERVICE_TYPE": "nacos",
        "APP_NAME": "test_app"
    }
    app = await run_serve(
        registry_type="nacos",
        service_modules=["tests.fixtures_service_module"],
        service_name="test_app",
        registry_config=registry_config,
        service_scheme=TransportSchemes.THRIFT,
        service_host="127.0.0.1",
        service_port=5010,
        service_weight=1,
        service_metadata={
            "version": "2.0.0",
            "description": "A test gRPC service",
        },
        task_manager_config=TaskManagerConfig()
    )

if __name__ == '__main__':
    asyncio.run(main())