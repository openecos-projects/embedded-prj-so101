# 默认目标，当你只敲 make 时执行
all: run

# 编译规则
servo_debug: servo_debug.c
	gcc servo_debug.c -o servo_debug

# 运行规则（依赖于编译规则，会自动先检查代码有没有更新）
run: servo_debug
	@echo "🔥 正在启动舵机调试工具..."
	sudo ./servo_debug

# 清理编译产物
clean:
	rm -f servo_debug
	@echo "🧹 清理完毕"

.PHONY: all run clean