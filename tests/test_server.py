import logging
import unittest

from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.registry import InMemoryServiceRegistry
from aduib_rpc.discover.registry.nacos.nacos import NacosServiceRegistry
from aduib_rpc.discover.service import AduibServiceFactory
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes
logging.basicConfig(level=logging.DEBUG)



# class TestAduibServiceFactoryAndInMemoryServiceRegistry(unittest.IsolatedAsyncioTestCase):
#     def setUp(self):
#         self.service = ServiceInstance(service_name='test_jsonrpc_app',host='localhost',port=5000,protocol=AIProtocols.AduibRpc,weight=1,scheme=TransportSchemes.JSONRPC)
#         self.registry = InMemoryServiceRegistry()
#         self.factory = AduibServiceFactory(service=self.service,registry=self.registry)
#
#     def test_run_server(self):
#         self.factory.run_server()
#
#     def test_register_service(self):
#         self.factory.register_service()
#
#     def test_deregister_service(self):
#         self.factory.register_service()
#         self.factory.deregister_service()
#
#
#     def test_discover_service(self):
#         self.factory.register_service()
#         discover_service = self.factory.discover_service()
#         assert self.service.service_name == discover_service.service_name
#
#
#
# class TestAduibServiceFactoryAndNacosServiceRegistry(unittest.IsolatedAsyncioTestCase):
#     def setUp(self):
#         self.service = ServiceInstance(service_name='test_jsonrpc_app',host='localhost',port=5000,protocol=AIProtocols.AduibRpc,weight=1,scheme=TransportSchemes.GRPC)
#         self.registry = NacosServiceRegistry(server_addresses='10.0.0.96:8848',namespace='eeb6433f-d68c-4b3b-a4a7-eeff19110e4d',group_name='DEFAULT_GROUP',username='nacos',password='nacos11.')
#         self.factory = AduibServiceFactory(service=self.service,registry=self.registry)
#
#     def test_run_server(self):
#         self.factory.run_server()
#         self.factory.register_service()
#
#     def test_register_service(self):
#         self.factory.register_service()
#
#     def test_deregister_service(self):
#         self.factory.register_service()
#         self.factory.deregister_service()
#
#
#     def test_discover_service(self):
#         discover_service = self.factory.discover_service()
#         print(discover_service)
