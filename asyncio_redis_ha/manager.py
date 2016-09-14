class ConnectionManager:
    def __init__(self, cluster_name: str, sentinels: list):
        self.cluster_name = cluster_name
        self.sentinels = sentinels
        self.master = None
        self.instances = []
