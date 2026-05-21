#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <string.h>

// ==========================================
// 1. 结构体定义 (含方向系数)
// ==========================================
typedef struct {
    int valid_min;  
    int valid_max;  
    int home_pos;   
    int dir;        // 1: 脉冲增大为正方向; -1: 脉冲减小为正方向
} ServoLimit;

// 🌟 终极校准数据：以你的收纳态脉冲为 Home，并对齐物理展开方向
ServoLimit arm_limits[6] = {
    // {最小值, 最大值, Home脉冲, 方向}
    {640,  3315, 640,   1},  // ID 1: 增大展开
    {136,  2511, 136,   1},  // ID 2: 增大展开
    {716,  2931, 2931, -1},  // ID 3: 减小展开 (dir=-1)
    {900,  2916, 2916, -1},  // ID 4: 减小展开 (dir=-1)
    {82,   3926, 84,   -1},  // ID 5: 减小展开 (dir=-1)
    {926,  2356, 926,   1}   // ID 6: 增大展开
};

// ==========================================
// 2. 底层驱动模块
// ==========================================

unsigned char calc_checksum(unsigned char *packet, int length) {
    int sum = 0;
    for (int i = 2; i < length - 1; i++) sum += packet[i];
    return (unsigned char)(~sum);
}

int init_serial(const char *device) {
    int fd = open(device, O_RDWR | O_NOCTTY | O_NDELAY);
    if (fd == -1) return -1;
    struct termios options;
    tcgetattr(fd, &options);
    cfsetispeed(&options, B1000000); cfsetospeed(&options, B1000000);
    options.c_cflag |= (CS8 | CLOCAL | CREAD);
    options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    options.c_oflag &= ~OPOST;
    tcsetattr(fd, TCSANOW, &options);
    return fd;
}

void _raw_set_servo_position(int fd, int id, int target_pos, int target_speed) {
    unsigned char cmd[13] = {0xFF, 0xFF, (unsigned char)id, 0x09, 0x03, 0x2A};
    cmd[6] = target_pos & 0xFF; cmd[7] = (target_pos >> 8) & 0xFF;
    cmd[10] = target_speed & 0xFF; cmd[11] = (target_speed >> 8) & 0xFF;
    cmd[12] = calc_checksum(cmd, 13);
    write(fd, cmd, 13);
}

int read_servo_position(int fd, int id) {
    unsigned char cmd[8] = {0xFF, 0xFF, id, 0x04, 0x02, 0x38, 0x02};
    cmd[7] = ~(cmd[2] + cmd[3] + cmd[4] + cmd[5] + cmd[6]) & 0xFF;
    tcflush(fd, TCIOFLUSH);
    write(fd, cmd, 8);
    unsigned char resp[8];
    int total = 0;
    for (int i = 0; i < 20; i++) {
        int n = read(fd, resp + total, 8 - total);
        if (n > 0) total += n;
        if (total >= 8) break;
        usleep(1000);
    }
    return (total >= 8 && resp[2] == id) ? (resp[5] | (resp[6] << 8)) : -1;
}

// ==========================================
// 3. 业务逻辑模块
// ==========================================

void safe_set_servo_position(int fd, int id, int target_pos, int target_speed) {
    if (id < 1 || id > 6) return;
    int clamped = target_pos;
    if (target_pos < arm_limits[id-1].valid_min) clamped = arm_limits[id-1].valid_min;
    if (target_pos > arm_limits[id-1].valid_max) clamped = arm_limits[id-1].valid_max;
    _raw_set_servo_position(fd, id, clamped, target_speed);
}

// 角度控制：正数角度统一对应“展开”物理动作
void safe_set_angle(int fd, int id, float angle_deg, int target_speed) {
    if (id < 1 || id > 6) return;
    int target_pos = arm_limits[id-1].home_pos + (int)(angle_deg * arm_limits[id-1].dir * 11.3777f);
    safe_set_servo_position(fd, id, target_pos, target_speed);
}

void print_all_status(int fd) {
    printf("\n--- 机械臂仪表盘 (收纳态应接近 0.0°) ---\n");
    for (int i = 1; i <= 6; i++) {
        int pos = read_servo_position(fd, i);
        if (pos != -1) {
            float angle = (float)(pos - arm_limits[i-1].home_pos) * arm_limits[i-1].dir / 11.3777f;
            printf("[ID %d] 脉冲: %-4d | 相对角度: %6.1f°\n", i, pos, angle);
        }
    }
}

// ==========================================
// 4. 主循环菜单
// ==========================================
int main() {
    int fd = init_serial("/dev/ttyACM0");
    if (fd == -1) { perror("串口打开失败"); return -1; }

    int choice;
    while(1) {
        printf("\n1. 归位(Home) | 2. 角度控制 | 5. 打印状态 | 6. 脉冲裸调 | 4. 退出\n选择: ");
        if (scanf("%d", &choice) != 1) break;

        switch(choice) {
            case 1:
                for (int i=1; i<=6; i++) safe_set_servo_position(fd, i, arm_limits[i-1].home_pos, 400);
                break;
            case 2: {
                int id; float ang;
                printf("ID (1-6): "); scanf("%d", &id);
                printf("展开角度 (正数): "); scanf("%f", &ang);
                safe_set_angle(fd, id, ang, 500);
                break;
            }
            case 5: print_all_status(fd); break;
            case 6: {
                int id, p;
                printf("ID: "); scanf("%d", &id);
                printf("脉冲值: "); scanf("%d", &p);
                safe_set_servo_position(fd, id, p, 500);
                break;
            }
            case 4: close(fd); return 0;
            default: printf("⚠️ 无效输入\n");
        }
    }
    return 0;
}