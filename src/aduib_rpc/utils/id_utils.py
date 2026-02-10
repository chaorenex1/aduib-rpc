
class IdUtils:
    @staticmethod
    def generate_client_id(prefix: str = "client") -> str:
        """Generate a unique client ID with the given prefix."""
        from aduib_rpc.utils.net_utils import NetUtils
        import uuid
        return f"{prefix}-{NetUtils.get_local_ip()}-{uuid.uuid4().hex[:8]}"