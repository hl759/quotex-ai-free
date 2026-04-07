class AlphaHiveError(Exception):
    pass

class DataUnavailableError(AlphaHiveError):
    pass

class InvalidSnapshotError(AlphaHiveError):
    pass
