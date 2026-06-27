from pathlib import Path

from moiraflow_worker.storage import upload_artifacts


class FakeS3:
    def __init__(self):
        self.uploaded = []
        self.buckets = set()

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise RuntimeError("no such bucket")

    def create_bucket(self, Bucket):
        self.buckets.add(Bucket)

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.uploaded.append((filename, bucket, key, ExtraArgs))


def test_upload_returns_refs_and_skips_missing(tmp_path):
    f = tmp_path / "out.csv"
    f.write_text("a,b,c\n1,2,3\n")
    s3 = FakeS3()

    refs = upload_artifacts(
        [str(f), str(tmp_path / "missing.txt")], "t1/job/abcd", client=s3, bucket="arts"
    )

    assert len(refs) == 1
    assert refs[0]["name"] == "out.csv"
    assert refs[0]["object_key"] == "t1/job/abcd/out.csv"
    assert refs[0]["content_type"] == "text/csv"
    assert refs[0]["size_bytes"] == Path(f).stat().st_size
    assert s3.uploaded[0][2] == "t1/job/abcd/out.csv"
    assert "arts" in s3.buckets  # bucket auto-created


def test_empty_paths_no_client_needed():
    assert upload_artifacts([], "x") == []
