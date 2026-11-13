# -*- coding: utf-8 -*-
"""NOVA one-click launcher: auto-starts the LAN server or finds an existing one."""
import socket
import threading
import time
import webbrowser
import os
import sys

PORT = 8765
DISCOVERY_PORT = 8766
DISCOVERY_MESSAGE = b"NOVA_LAN_DISCOVER_V1"
BASE = os.path.dirname(os.path.abspath(__file__))

def discover_server(timeout=2.0):
    """Find an already running NOVA server on the local network without asking for an IP."""
    found = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.25)
        sock.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))
        # Some Wi-Fi routers handle subnet broadcast better than limited broadcast.
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            parts = local_ip.split(".")
            if len(parts) == 4:
                sock.sendto(DISCOVERY_MESSAGE, (".".join(parts[:3]) + ".255", DISCOVERY_PORT))
        except Exception:
            pass
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, address = sock.recvfrom(1024)
                if data.startswith(b"NOVA_LAN_HERE"):
                    found.append(address[0])
                    break
            except socket.timeout:
                continue
    except OSError:
        pass
    finally:
        sock.close()
    return found[0] if found else None

def start_discovery_responder():
    def worker():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            while True:
                data, addr = s.recvfrom(1024)
                if data == DISCOVERY_MESSAGE:
                    try:
                        s.sendto(b"NOVA_LAN_HERE", addr)
                    except OSError:
                        pass
        except OSError as exc:
            print("Служба автообнаружения:", exc)
        finally:
            s.close()
    threading.Thread(target=worker, daemon=True).start()

def main():
    os.chdir(BASE)
    print()
    print("=" * 58)
    print("             NOVA MESSENGER — БЫСТРЫЙ ЗАПУСК")
    print("=" * 58)
    print("Ищем уже работающий NOVA-сервер в вашей локальной сети...")
    # If this computer already hosts NOVA, reuse it even if broadcast discovery is blocked.
    host = None
    try:
        test = socket.create_connection(("127.0.0.1", PORT), timeout=0.35)
        test.close()
        host = "127.0.0.1"
    except OSError:
        host = discover_server()

    if host:
        url = "http://%s:%s" % (host, PORT)
        print("Сервер найден автоматически:", url)
        webbrowser.open(url)
        print("Мессенджер открыт. Это окно можно закрыть.")
        time.sleep(2)
        return

    print("Сервер не найден. Запускаем его на этом компьютере...")
    try:
        import server
        httpd = server.create_server(("0.0.0.0", PORT))
    except OSError as exc:
        print()
        print("Не удалось запустить сервер:", exc)
        print("Возможно, порт 8765 уже занят другой программой.")
        input("Нажмите Enter, чтобы закрыть окно...")
        return

    start_discovery_responder()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    url = "http://127.0.0.1:%s" % PORT
    print()
    print("NOVA готов к работе!")
    print("На этом компьютере открылся:", url)
    try:
        ip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip.connect(("8.8.8.8", 80))
        lan_ip = ip.getsockname()[0]
        ip.close()
        print("Другие устройства найдут сервер автоматически.")
        print("Если потребуется адрес вручную: http://%s:%s" % (lan_ip, PORT))
    except OSError:
        print("Другие устройства найдут сервер автоматически.")
    print()
    print("НЕ ЗАКРЫВАЙТЕ ЭТО ЧЁРНОЕ ОКНО, ПОКА ОБЩАЕТЕСЬ.")
    print("Чтобы выключить сервер, закройте это окно.")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()

if __name__ == "__main__":
    main()
