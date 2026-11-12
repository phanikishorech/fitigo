"""Bounded format checks with stdlib only; not a malware scanner or full decoder."""
import struct
import zlib
from fastapi import HTTPException

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def validate_image(upload):
    upload.file.seek(0)
    data = upload.file.read(MAX_BYTES + 1)
    upload.file.seek(0)
    if len(data) > MAX_BYTES: raise HTTPException(400, 'File too large')
    mime = upload.content_type
    try:
        if mime == 'image/png':
            assert data.startswith(b'\x89PNG\r\n\x1a\n')
            pos, width, height, idat, ended = 8, 0, 0, False, False
            first = True
            while pos < len(data):
                length = struct.unpack('>I', data[pos:pos+4])[0]
                kind, payload = data[pos+4:pos+8], data[pos+8:pos+8+length]
                assert len(payload) == length
                crc = struct.unpack('>I', data[pos+8+length:pos+12+length])[0]
                assert zlib.crc32(kind + payload) & 0xffffffff == crc
                if first:
                    assert kind == b'IHDR' and length == 13
                    width, height = struct.unpack('>II', payload[:8]); first = False
                if kind == b'IDAT': idat = True
                pos += length + 12
                if kind == b'IEND': assert length == 0; ended = True; break
            assert ended and idat and pos == len(data) and 0 < width * height <= MAX_PIXELS
        elif mime == 'image/jpeg':
            assert data[:2] == b'\xff\xd8' and data[-2:] == b'\xff\xd9'
            pos, dimensions, scan = 2, False, False
            while pos < len(data)-2:
                assert data[pos] == 255
                while data[pos] == 255: pos += 1
                marker = data[pos]; pos += 1
                length = int.from_bytes(data[pos:pos+2], 'big')
                assert length >= 2 and pos + length <= len(data)
                if marker in {0xc0, 0xc1, 0xc2}:
                    assert length >= 8
                    height = int.from_bytes(data[pos+3:pos+5], 'big'); width = int.from_bytes(data[pos+5:pos+7], 'big')
                    assert 0 < width * height <= MAX_PIXELS; dimensions = True
                if marker == 0xda: scan = True; break
                pos += length
            assert dimensions and scan
        elif mime == 'image/webp':
            assert data[:4] == b'RIFF' and data[8:12] == b'WEBP' and int.from_bytes(data[4:8], 'little') + 8 == len(data)
            pos, found = 12, False
            while pos < len(data):
                kind = data[pos:pos+4]; size = int.from_bytes(data[pos+4:pos+8], 'little')
                assert size > 0 and pos + 8 + size <= len(data)
                if kind == b'VP8 ':
                    chunk = data[pos+8:pos+8+size]; assert len(chunk) >= 10 and chunk[3:6] == b'\x9d\x01\x2a'
                    width = int.from_bytes(chunk[6:8], 'little') & 0x3fff; height = int.from_bytes(chunk[8:10], 'little') & 0x3fff
                    assert 0 < width * height <= MAX_PIXELS; found = True
                elif kind == b'VP8L':
                    chunk = data[pos+8:pos+8+size]; assert len(chunk) >= 5 and chunk[0] == 47
                    bits = int.from_bytes(chunk[1:5], 'little'); assert ((bits & 0x3fff)+1) * (((bits >> 14)&0x3fff)+1) <= MAX_PIXELS; found = True
                elif kind == b'ANIM': raise ValueError('Animated uploads are unsupported')
                pos += 8 + size + (size % 2)
            assert found and pos == len(data)
        else: raise ValueError('Unsupported type')
    except (AssertionError, ValueError, IndexError, struct.error):
        raise HTTPException(400, 'Invalid or unsupported image content; use a static JPEG, PNG or WebP up to 16 megapixels.') from None