# 运行完立刻退出
print("hello")

# 永远不退出，也没有监听端口，相当于 Node 里的 setInterval
import time
while True:
    print("tick")
    time.sleep(1)