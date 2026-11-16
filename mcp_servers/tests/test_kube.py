import json

from kubernetes_asyncio.client.exceptions import ApiException

from hoa_mcp.k8s_read.kube import KubeError


def test_kube_error_takes_the_message_from_the_api_body():
    exc = ApiException(status=403, reason="Forbidden")
    exc.body = json.dumps({"message": 'secrets is forbidden: User "x" cannot list secrets'})
    error = KubeError.from_api(exc)
    assert error.status == 403
    assert str(error) == 'kubernetes API 403: secrets is forbidden: User "x" cannot list secrets'


def test_kube_error_falls_back_to_the_reason_without_a_body():
    error = KubeError.from_api(ApiException(status=404, reason="Not Found"))
    assert str(error) == "kubernetes API 404: Not Found"
