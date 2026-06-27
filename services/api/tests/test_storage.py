from moiraflow_api.storage import presigned_url


def test_presigned_url_is_offline_signed_url():
    # boto3 presigning is local (no network); returns a signed GET URL on the public endpoint.
    url = presigned_url("a/job/out.csv", "moiraflow-artifacts")
    assert url.startswith("http://localhost:9000/")
    assert "moiraflow-artifacts" in url
    assert "X-Amz-Signature" in url
