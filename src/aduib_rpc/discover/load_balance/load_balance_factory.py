from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.discover.load_balance import LoadBalancer
from aduib_rpc.utils.constant import LoadBalancePolicy


class LoadBalancerFactory:
    """ Factory class to create load balancer instances based on the specified strategy."""

    @classmethod
    def get_load_balancer(cls, policy: LoadBalancePolicy)->LoadBalancer:
        """ Returns an instance of the load balancer based on the specified policy.

        Args:
            cls: The class type of the load balancer to be instantiated.
            policy (str): The load balancing strategy to be used.
                                     Supported values are 'RoundRobin' and 'Random'.
            services (list[ServiceInstance]): A list of service instances to balance the load across.

        Returns:
            An instance of the specified load balancer class.

        Raises:
            ValueError: If an unsupported load balancing policy is provided.
        """
        match policy:
            case LoadBalancePolicy.Random:
                from .load_balance import RandomLB
                return RandomLB()
            case LoadBalancePolicy.WeightedRoundRobin:
                from .load_balance import WeightedRoundRobinLB
                return WeightedRoundRobinLB()
            case LoadBalancePolicy.CONSISTENT_HASHING:
                from .load_balance import ConsistentHashLB
                return ConsistentHashLB()
            case _:
                raise ValueError(f"Unsupported load balancing policy: {policy}")