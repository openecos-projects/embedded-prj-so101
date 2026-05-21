#include "main.h"

#define RX_BUF_SIZE 64

// ==========================================
// 1. 舵机底层驱动 (保持不变)
// ==========================================
uint8_t calc_checksum(uint8_t *packet, int length) {
    int sum = 0;
    for (int i = 2; i < length - 1; i++) sum += packet[i];
    return (uint8_t)(~sum);
}

void send_servo_cmd(uint8_t id, uint16_t target_pos, uint16_t target_speed) {
    uint8_t cmd[13] = {0xFF, 0xFF, id, 0x09, 0x03, 0x2A};
    cmd[6] = target_pos & 0xFF; 
    cmd[7] = (target_pos >> 8) & 0xFF;
    cmd[10] = target_speed & 0xFF; 
    cmd[11] = (target_speed >> 8) & 0xFF;
    cmd[12] = calc_checksum(cmd, 13);
    for (int i = 0; i < 13; i++) hp_uart_send((char)cmd[i]);
}

// ==========================================
// 2. 核心：纯手动字符解析逻辑 (不依赖 stdlib)
// ==========================================
void parse_and_execute(char *buf) {
    uint16_t pulses[6] = {0, 0, 0, 0, 0, 0};
    int p_idx = 0;
    char *ptr = buf;

    // 🌟 在串口打印接收到的原始整行字符串，方便对齐
    printf("\n[Recv raw]: %s\n", buf); 

    while (*ptr != '\0' && p_idx < 6) {
        if (*ptr < '0' || *ptr > '9') {
            ptr++;
            continue;
        }

        uint32_t val = 0;
        while (*ptr >= '0' && *ptr <= '9') {
            val = val * 10 + (*ptr - '0');
            ptr++;
        }
        
        pulses[p_idx] = (uint16_t)val;
        
        // 🌟 打印解析出来的每一个 ID 的值
        printf("  -> ID%d PWM: %u\n", p_idx + 1, pulses[p_idx]);
        
        p_idx++;

        if (*ptr == ',') ptr++;
    }

    // 解析满 6 个才下发，防止数据不全导致舵机乱抖
    if (p_idx == 6) {
        for (int i = 0; i < 6; i++) {
            send_servo_cmd(i + 1, pulses[i], 0);
        }
        printf(">> PWM Dispatched to All Servos!\n");
    } else {
        printf("!! Error: Only parsed %d values, ignore this frame.\n", p_idx);
    }
}

// ==========================================
// 3. 主循环
// ==========================================
void main(void){
    char rx_buf[RX_BUF_SIZE];
    int rx_idx = 0;
    char recv_char;

    // 初始化硬件
    sys_uart_init();           
    hp_uart_init(1000000);     
    
    // 开机盲归位初值
    uint16_t home_vals[6] = {644, 137, 2950, 2924, 102, 947};
    for (int i = 1; i <= 6; i++) send_servo_cmd(i, home_vals[i-1], 1000);
    delay_ms(1500);

    while(1) {
        // 阻塞式接收来自 K230 的字符
        hp_uart_recv(&recv_char); 

        // 遇到换行符说明一帧数据结束
        if (recv_char == '\n' || recv_char == '\r') {
            if (rx_idx > 0) {
                rx_buf[rx_idx] = '\0';
                parse_and_execute(rx_buf); 
                rx_idx = 0;
            }
        } else {
            // 只接收有效字符：数字和逗号
            if (rx_idx < RX_BUF_SIZE - 1 && ((recv_char >= '0' && recv_char <= '9') || recv_char == ',')) {
                rx_buf[rx_idx++] = recv_char;
            } else if ((uint8_t)recv_char > 127) {
                // 如果混入二进制协议包头，直接重置
                rx_idx = 0;
            }
        }
    }
}