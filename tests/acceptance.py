#!/usr/bin/env python3
"""Local acceptance regression. Standard library only; never claims two-PC proof."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time


def frame(kind, payload=b''):
    return struct.pack('>I', len(payload) + 1) + bytes([kind]) + payload


def wav(bits, pcm, extra=False):
    fmt = struct.pack('<HHIIHH', 1, 1, 16000, 16000 * bits // 8, bits // 8, bits)
    other = b'LIST\x04\0\0\0INFO' if extra else b''
    body = b'WAVEfmt ' + struct.pack('<I', 16) + fmt + other
    body += b'data' + struct.pack('<I', len(pcm)) + pcm + (b'\0' if len(pcm) % 2 else b'')
    body += other
    return b'RIFF' + struct.pack('<I', len(body)) + body


def samples():
    return {'empty.txt': b'', 'single.bin': b'A' * 10000,
            'all.bin': bytes(range(256)) * 4096,
            'mixed.txt': b'\xef\xbb\xbf' + ('AéΩ中文😀𠮷👨‍👩‍👧\r\n' * 35000).encode(),
            'invalid.txt': b'abc\xc0\x80def',
            'pcm16.wav': wav(16, b'\x01\0\x02\0' * 300000, True),
            'pcm8.wav': wav(8, bytes(range(256)) * 4096),
            'odd.wav': wav(16, b'\x01\0\xff', True),
            '20mb.bin': b'AB' * 10000000}


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def connect(p):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        try:
            return socket.create_connection(('127.0.0.1', p), timeout=2)
        except ConnectionRefusedError:
            time.sleep(.03)
    raise AssertionError('listener did not start')


def recv_exact(sock, count):
    data = b''
    while len(data) < count:
        part = sock.recv(count - len(data))
        assert part, 'connection closed before ACK completed'
        data += part
    return data


def stats(text):
    lines = re.findall(r'STATS [^\r\n]*', text)
    assert len(lines) == 1, text[-2000:]
    return dict(item.split('=', 1) for item in lines[0].split()[1:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default='./textlink.exe' if os.name == 'nt' else './textlink')
    ap.add_argument('--json', default='results/acceptance.json')
    args = ap.parse_args()
    dest = Path(args.json)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists(): dest.unlink()
    logdir = dest.parent / 'acceptance_logs'
    logdir.mkdir(parents=True, exist_ok=True)
    exe = str(Path(args.exe).resolve())
    rows = []
    children = []
    logs = []
    dataset = samples()
    with tempfile.TemporaryDirectory(prefix='textlink-test-') as tmp:
        root = Path(tmp)
        def spawn(command, name, chat=False):
            log = open(root / (name + '.log'), 'w+b')
            logs.append(log)
            proc = subprocess.Popen([exe] + command, cwd=root,
                                    stdin=subprocess.PIPE if chat else subprocess.DEVNULL,
                                    stdout=log, stderr=log)
            children.append(proc)
            return proc, log
        def output(log):
            log.flush(); log.seek(0)
            return log.read().decode('utf-8', 'replace')
        def record(name, **details):
            rows.append(dict(test=name, passed=True, **details))
            print('PASS', name, flush=True)
        try:
            for name, data in dataset.items():
                source = root / name; source.write_bytes(data)
                for mode in ('raw', 'huff'):
                    p = port(); out = root / (name + '-' + mode)
                    recv, log = spawn(['recv', str(p), str(out)], name + mode)
                    time.sleep(.15)
                    sent = subprocess.run([exe, 'send', '127.0.0.1', str(p), str(source), '--' + mode],
                                          cwd=root, capture_output=True, timeout=120)
                    recv.wait(timeout=120)
                    assert sent.returncode == recv.returncode == 0
                    assert (out / name).read_bytes() == data
                    ss = stats(sent.stderr.decode('utf-8', 'replace')); rs = stats(output(log))
                    assert ss['wire_bytes'] == rs['wire_bytes']
                    expected = int(ss['wire_bytes']) / len(data) if data else 0
                    assert abs(float(ss['ratio']) - expected) <= .000051
                    if mode == 'huff':
                        want = 'char' if name in ('mixed.txt', 'empty.txt') else 's16' if name in ('pcm16.wav', 'odd.wav') else 'byte'
                        assert ss['sym'] == want, (name, ss)
                        if name == 'mixed.txt': assert float(ss['ratio']) < .55
                    record(name + ':' + mode, sha256=hashlib.sha256(data).hexdigest(), send=ss, recv=rs)
                    log.close()

            # The same two real C chat processes exercise both /send modes and ACKs.
            for mode in ('raw', 'huff'):
                p = port()
                server, slog = spawn(['chat', 'server', str(p), '--' + mode], 'chat-server-' + mode, True)
                time.sleep(.15)
                client, clog = spawn(['chat', 'client', '127.0.0.1', str(p), '--' + mode], 'chat-client-' + mode, True)
                time.sleep(.3)
                message = 'Hello é Ω 中文 😀 𠮷'
                for process in (server, client):
                    process.stdin.write((message + '\n').encode()); process.stdin.flush()
                for name in ('mixed.txt', 'pcm16.wav'):
                    target = root / 'received' / name
                    if target.exists(): target.unlink()
                    client.stdin.write(('/' + mode + '\n/send ' + str(root / name) + '\n').encode())
                    client.stdin.flush()
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if target.exists() and target.read_bytes() == dataset[name]: break
                        time.sleep(.05)
                    else: raise AssertionError('chat file did not arrive: ' + name)
                    time.sleep(.6)  # allow ACK handling before next /send
                    record('chat-send:' + name + ':' + mode, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
                client.stdin.write(b'/quit\n'); client.stdin.flush()
                client.wait(timeout=5)
                server.communicate(input=b'\n', timeout=5)
                assert message in output(slog) and message in output(clog)
                assert '對方已成功還原並存檔' in output(clog)
                record('chat-roundtrip:' + mode)
                slog.close(); clog.close()

            for mode in ('raw', 'huff'):
                p = port()
                server, log = spawn(['chat', 'server', str(p), '--' + mode], 'chunks-' + mode, True)
                with connect(p) as sock:
                    message = 'chunk é 中文 😀 𠮷'
                    server.stdin.write((message + '\n').encode()); server.stdin.flush()
                    def exact(n):
                        data = b''
                        while len(data) < n:
                            part = sock.recv(n - len(data))
                            assert part
                            data += part
                        return data
                    hdr = exact(5)
                    blob = hdr + exact(struct.unpack('>I', hdr[:4])[0] - 1)
                    sock.sendall(blob * 5)
                    for byte in blob:
                        sock.sendall(bytes([byte])); time.sleep(.001)
                    sock.sendall(frame(1, b'\xc0\x80'))
                    sock.sendall(frame(1, b'AFTER_INVALID_UTF8'))
                    time.sleep(.3)
                server.communicate(input=b'\n', timeout=5)
                text = output(log)
                assert text.count(message) >= 7
                assert 'AFTER_INVALID_UTF8' in text and '不是合法 UTF-8' in text
                record('sticky-drip-and-invalid-utf8:' + mode)
                log.close()

            begin = lambda name, n=3: frame(16, b'\0' + struct.pack('>QQ', n, n) + name.encode())
            p = port(); out = root / 'drip-file'
            recv, log = spawn(['recv', str(p), str(out)], 'drip-file')
            with connect(p) as sock:
                blob = begin('fragment.bin') + frame(17, b'a') + frame(17, b'bc') + frame(18)
                for byte in blob: sock.sendall(bytes([byte])); time.sleep(.001)
                assert recv_exact(sock, 6) == frame(18, b'\0')
            recv.wait(timeout=5)
            assert recv.returncode == 0 and (out / 'fragment.bin').read_bytes() == b'abc'
            record('file-byte-drip', recv=stats(output(log)))
            log.close()

            p = port()
            server, log = spawn(['chat', 'server', str(p)], 'chat-malformed-end', True)
            with connect(p) as sock:
                sock.sendall(begin('rejected.bin') + frame(17, b'abc') + frame(18, b'junk'))
                assert recv_exact(sock, 6) == frame(18, b'\1')
            server.communicate(input=b'\n', timeout=5)
            assert not (root / 'received' / 'rejected.bin').exists()
            record('chat-reject-nonempty-end')
            log.close()

            corrupt = b'HFS1' + struct.pack('<IIIII', 0, 1, 0, 1, 1) + struct.pack('<II', 65, 0) + b'\0'
            cases = {'zero': b'\0\0\0\0\1', 'oversize': struct.pack('>I', 16777217) + b'\1',
                     'unknown-header-only': struct.pack('>I', 1000) + b'\x7f',
                     'disconnect': begin('bad.bin', 100) + frame(17, b'abc'),
                     'nonempty-end': begin('bad.bin') + frame(17, b'abc') + frame(18, b'junk'),
                     'bad-codebook': frame(16, b'\1' + struct.pack('>QQ', 1, len(corrupt)) + b'bad.bin') + frame(17, corrupt) + frame(18)}
            for name, blob in cases.items():
                p = port(); out = root / ('bad-' + name)
                recv, log = spawn(['recv', str(p), str(out)], name)
                with connect(p) as sock:
                    sock.sendall(blob)
                    if name == 'unknown-header-only':
                        assert sock.recv(1) == b'', 'unknown header must close without waiting for payload'
                    else: sock.shutdown(socket.SHUT_WR)
                recv.wait(timeout=5)
                assert recv.returncode == 1
                assert not out.exists() or not list(out.iterdir())
                assert '錯誤' in output(log)
                record('reject:' + name, exit_code=recv.returncode)
                log.close()
        finally:
            for child in children:
                if child.poll() is None: child.kill(); child.wait()
            for log in logs:
                if not log.closed: log.close()
            for source in root.glob('*.log'):
                (logdir / source.name).write_bytes(source.read_bytes())
    dest.write_text(json.dumps({'environment': 'loopback-only', 'tests': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Acceptance:', len(rows), 'PASS; loopback only')


if __name__ == '__main__':
    main()
