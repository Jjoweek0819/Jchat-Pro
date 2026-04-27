import socket

VOICE_HOST = '0.0.0.0'
VOICE_PORT = 5006

def start_voice_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((VOICE_HOST, VOICE_PORT))

    # room_clients: { room_id: set((ip, port)) }
    room_clients: dict = {}
    # addr_room:   { (ip, port): room_id }
    addr_room:   dict = {}

    print(f"【語音伺服器】啟動於 UDP port {VOICE_PORT}（支援分房）")

    while True:
        try:
            data, addr = sock.recvfrom(65536)

            # ── 加入/切換房間 ──────────────────────────────
            if data.startswith(b'JOIN:'):
                room_id = data[5:].decode('utf-8', errors='replace').strip()
                if not room_id:
                    continue
                # 從舊房間移除
                old_room = addr_room.get(addr)
                if old_room and old_room in room_clients:
                    room_clients[old_room].discard(addr)
                    if not room_clients[old_room]:
                        del room_clients[old_room]
                # 加入新房間
                room_clients.setdefault(room_id, set()).add(addr)
                addr_room[addr] = room_id
                cnt = len(room_clients[room_id])
                print(f"[語音] {addr} 加入 '{room_id}'  該房 {cnt} 人")
                continue

            # ── 離開 ──────────────────────────────────────
            if data == b'LEAVE':
                old_room = addr_room.pop(addr, None)
                if old_room and old_room in room_clients:
                    room_clients[old_room].discard(addr)
                    if not room_clients[old_room]:
                        del room_clients[old_room]
                print(f"[語音] {addr} 離開")
                continue

            # ── 心跳（忽略）───────────────────────────────
            if data == b'PING':
                continue

            # ── 音訊：只轉發給同房間其他人 ─────────────────
            room_id = addr_room.get(addr)
            if not room_id:
                continue
            dead_peers = set()
            for peer in list(room_clients.get(room_id, set())):
                if peer != addr:
                    try:
                        sock.sendto(data, peer)
                    except OSError as e:
                        # WinError 10054：對方已斷線，移除這個 peer
                        if getattr(e, 'winerror', None) == 10054:
                            dead_peers.add(peer)
                        else:
                            print(f"[語音] 轉發失敗 {peer}: {e}")
                    except Exception as e:
                        print(f"[語音] 轉發失敗 {peer}: {e}")
            # 清除失效的 peer
            for peer in dead_peers:
                room_clients.get(room_id, set()).discard(peer)
                old_r = addr_room.pop(peer, None)
                print(f"[語音] 自動移除失效 peer {peer}")

        except Exception as e:
            print(f"[語音] 錯誤: {e}")

if __name__ == '__main__':
    start_voice_server()
