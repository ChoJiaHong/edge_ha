from Controller.optimizer import optimize


def test_optimize_success_default():
    services = [
        {
            "podIP": "ip1",
            "hostPort": 1,
            "serviceType": "object",
            "currentConnection": 0,
            "nodeName": "node1",
            "hostIP": "host1",
            "frequencyLimit": [5, 3],
            "currentFrequency": 5,
            "workloadLimit": 20,
        }
    ]
    status, updated = optimize("object", 2, services)
    assert status == "success"
    assert updated[0]["currentConnection"] == 2
    assert updated[0]["currentFrequency"] == 5


def test_optimize_reduce_frequency():
    services = [
        {
            "podIP": "ip1",
            "hostPort": 1,
            "serviceType": "object",
            "currentConnection": 0,
            "nodeName": "node1",
            "hostIP": "host1",
            "frequencyLimit": [5, 3],
            "currentFrequency": 5,
            "workloadLimit": 20,
        }
    ]
    status, updated = optimize("object", 5, services)
    assert status == "success"
    assert updated[0]["currentConnection"] == 5
    assert updated[0]["currentFrequency"] == 4
