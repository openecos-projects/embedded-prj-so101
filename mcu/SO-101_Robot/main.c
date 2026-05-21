#include "main.h"

// ==========================================
// 1. 工具宏与全局配置
// ==========================================
#define MY_ABS(x) ((x) > 0 ? (x) : -(x))
#define FREQ_MS   15    // 手柄采样周期

// ==========================================
// 2. 结构体与校准数据 (基于实测仪表盘)
// ==========================================
typedef struct {
    uint16_t valid_min;  
    uint16_t valid_max;  
    uint16_t home_pos;   
    int      dir;        // 1: 增大展开; -1: 减小展开
    int      step;       // 步进速度
} ServoLimit;

// 🌟 终极校准矩阵：ID 3/4/5 已设为反向，5号舵机已限速
ServoLimit arm_limits[6] = {
    // {min, max, home, dir, step}
    {640,  3315, 644,   1, 35},  // ID 1: 左/右
    {136,  2511, 137,   1, 35},  // ID 2: L1/L2
    {716,  2950, 2950, -1, 35},  // ID 3: R1/R2
    {900,  2924, 2924, -1, 35},  // ID 4: 上/下
    {82,   3926, 102,  -1, 35},  // ID 5: 三角/X 
    {926,  2356, 947,   1, 35}   // ID 6: 方框/圆圈
};

uint16_t current_pos[6]; // 6路舵机的当前目标脉冲

// ==========================================
// 3. 舵机底层驱动 (适配 hp_uart)
// ==========================================

uint8_t calc_checksum(uint8_t *packet, int length) {
    int sum = 0;
    for (int i = 2; i < length - 1; i++) sum += packet[i];
    return (uint8_t)(~sum);
}

// 下发位置指令
void send_servo_cmd(uint8_t id, uint16_t target_pos, uint16_t target_speed) {
    // 第一层拦截：安全钳位
    if (target_pos < arm_limits[id-1].valid_min) target_pos = arm_limits[id-1].valid_min;
    if (target_pos > arm_limits[id-1].valid_max) target_pos = arm_limits[id-1].valid_max;

    uint8_t cmd[13] = {0xFF, 0xFF, id, 0x09, 0x03, 0x2A};
    cmd[6] = target_pos & 0xFF; 
    cmd[7] = (target_pos >> 8) & 0xFF;
    cmd[10] = target_speed & 0xFF; 
    cmd[11] = (target_speed >> 8) & 0xFF;
    cmd[12] = calc_checksum(cmd, 13);
    for (int i = 0; i < 13; i++) hp_uart_send((char)cmd[i]);
}

// 读取当前位置
int16_t read_servo_pos(uint8_t id) {
    uint8_t cmd[8] = {0xFF, 0xFF, id, 0x04, 0x02, 0x38, 0x02};
    cmd[7] = calc_checksum(cmd, 8);
    for (int i = 0; i < 8; i++) hp_uart_send((char)cmd[i]);
    delay_ms(2);
    char dummy;
    for (int i = 0; i < 8; i++) hp_uart_recv(&dummy); // 丢弃回声
    uint8_t resp[8]; char c;
    for (int i = 0; i < 8; i++) {
        hp_uart_recv(&c);
        resp[i] = (uint8_t)c;
    }
    if (resp[0] == 0xFF && resp[1] == 0xFF && resp[2] == id) return (int16_t)(resp[5] | (resp[6] << 8));
    return -1;
}

// ==========================================
// 4. 核心：带实时监控的高速归位
// ==========================================
void home_with_monitor(void) {
    printf("\n>> Start Sync Home\n");
    for (int i = 1; i <= 6; i++) send_servo_cmd(i, arm_limits[i-1].home_pos, 0);
    delay_ms(3000);
    for (int i = 0; i < 6; i++) current_pos[i] = arm_limits[i].home_pos;
    printf(">> All Ready!\n");
}

// ==========================================
// 5. 主程序主循环
// ==========================================
void main(void){
    uint8_t ps2_data[9];
    sys_uart_init();
    hp_uart_init(1000000); 
    ps2_init();
    
    home_with_monitor();

    while(1) {
        if(ps2_read_packet(ps2_data)) {
            int btn1 = (int)(~ps2_data[3]);
            int btn2 = (int)(~ps2_data[4]);

            if(btn1 != 0 || btn2 != 0) {
                printf("Key:%x %x\n", btn1, btn2);

                // 🌟 遍历 6 个关节，统一计算目标位置
                for (int i = 0; i < 6; i++) {
                    int32_t next = (int32_t)current_pos[i]; // 使用 32 位带符号数防止溢出
                    int move = 0;

                    // 映射手柄逻辑
                    switch(i + 1) {
                        case 1: // ID 1: 左/右
                            if(btn1 & 0x80) { next -= (arm_limits[0].step * arm_limits[0].dir); move = 1; }
                            if(btn1 & 0x20) { next += (arm_limits[0].step * arm_limits[0].dir); move = 1; }
                            break;
                        case 4: // ID 4: 上/下
                            if(btn1 & 0x10) { next += (arm_limits[3].step * arm_limits[3].dir); move = 1; }
                            if(btn1 & 0x40) { next -= (arm_limits[3].step * arm_limits[3].dir); move = 1; }
                            break;
                        case 2: // ID 2: L1/L2
                            if(btn2 & 0x04) { next += (arm_limits[1].step * arm_limits[1].dir); move = 1; }
                            if(btn2 & 0x01) { next -= (arm_limits[1].step * arm_limits[1].dir); move = 1; }
                            break;
                        case 3: // ID 3: R1/R2
                            if(btn2 & 0x08) { next += (arm_limits[2].step * arm_limits[2].dir); move = 1; }
                            if(btn2 & 0x02) { next -= (arm_limits[2].step * arm_limits[2].dir); move = 1; }
                            break;
                        case 5: // ID 5: 三角/X
                            if(btn2 & 0x10) { next += (arm_limits[4].step * arm_limits[4].dir); move = 1; }
                            if(btn2 & 0x40) { next -= (arm_limits[4].step * arm_limits[4].dir); move = 1; }
                            break;
                        case 6: // ID 6: 方框/圆圈
                            if(btn2 & 0x80) { next += (arm_limits[5].step * arm_limits[5].dir); move = 1; }
                            if(btn2 & 0x20) { next -= (arm_limits[5].step * arm_limits[5].dir); move = 1; }
                            break;
                    }

                    if (move) {
                        // 🌟 核心保护：在赋值回 uint16 之前先行锁死范围，彻底解决回绕Bug
                        if (next < (int32_t)arm_limits[i].valid_min) next = arm_limits[i].valid_min;
                        if (next > (int32_t)arm_limits[i].valid_max) next = arm_limits[i].valid_max;
                        current_pos[i] = (uint16_t)next;
                    }
                }

                if(btn1 & 0x01) home_with_monitor(); // SELECT 归位

                // 统一刷新所有舵机
                for(int j=1; j<=6; j++) send_servo_cmd(j, current_pos[j-1], 0);
            }
        }
        delay_ms(FREQ_MS); 
    }
}