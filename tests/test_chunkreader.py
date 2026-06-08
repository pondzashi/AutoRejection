import os
import tempfile
from scripts.auto_validate import ChunkReader


def test_chunkreader_iterates_and_respects_chunk_size():
    data = "a,b\nc,d\ne,f\n"
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
        tf.write(data)
        tf_path = tf.name

    try:
        reader = ChunkReader(tf_path, col_delimiter=",", chunk_size=2, encoding="utf-8")
        chunks = list(reader)
        # Expect two chunks: first with 2 rows, second with 1 row
        assert len(chunks) == 2
        (first_chunk, start1) = chunks[0]
        (second_chunk, start2) = chunks[1]
        assert len(first_chunk) == 2
        assert len(second_chunk) == 1
        assert start1 == 1
        assert start2 == 3
    finally:
        os.remove(tf_path)
