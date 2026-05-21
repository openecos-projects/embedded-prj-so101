from libs.PipeLine import PipeLine, ScopedTiming
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
import os
import ujson
from media.media import *
from time import *
import nncase_runtime as nn
import ulab.numpy as np
import time
import image
import aicube
import random
import gc
import sys

# 🌟 组长增加的串口库
from machine import UART
from machine import FPIOA
import math

# =========================================================================
# （中间的类定义 HandDetApp, HandKPClassApp, HandKeyPointClass 完全保持不变）
# 为了排版简洁，这里省略上面那几百行类的代码，你直接用你原来的那部分
# =========================================================================
class HandDetApp(AIBase):
    def __init__(self,kmodel_path,labels,model_input_size,anchors,confidence_threshold=0.2,nms_threshold=0.5,nms_option=False, strides=[8,16,32],rgb888p_size=[1920,1080],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.labels=labels
        self.model_input_size=model_input_size
        self.confidence_threshold=confidence_threshold
        self.nms_threshold=nms_threshold
        self.anchors=anchors
        self.strides = strides
        self.nms_option = nms_option
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        self.ai2d=Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right = self.get_padding_param()
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            dets = aicube.anchorbasedet_post_process(results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides, len(self.labels), self.confidence_threshold, self.nms_threshold, self.anchors, self.nms_option)
            return dets

    def get_padding_param(self):
        dst_w = self.model_input_size[0]
        dst_h = self.model_input_size[1]
        input_width = self.rgb888p_size[0]
        input_high = self.rgb888p_size[1]
        ratio_w = dst_w / input_width
        ratio_h = dst_h / input_high
        if ratio_w < ratio_h:
            ratio = ratio_w
        else:
            ratio = ratio_h
        new_w = int(ratio * input_width)
        new_h = int(ratio * input_high)
        dw = (dst_w - new_w) / 2
        dh = (dst_h - new_h) / 2
        top = int(round(dh - 0.1))
        bottom = int(round(dh + 0.1))
        left = int(round(dw - 0.1))
        right = int(round(dw + 0.1))
        return top, bottom, left, right

class HandKPClassApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,rgb888p_size=[1920,1080],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.model_input_size=model_input_size
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.crop_params=[]
        self.debug_mode=debug_mode
        self.ai2d=Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    def config_preprocess(self,det,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            self.crop_params = self.get_crop_param(det)
            self.ai2d.crop(self.crop_params[0],self.crop_params[1],self.crop_params[2],self.crop_params[3])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            results=results[0].reshape(results[0].shape[0]*results[0].shape[1])
            results_show = np.zeros(results.shape,dtype=np.int16)
            results_show[0::2] = results[0::2] * self.crop_params[3] + self.crop_params[0]
            results_show[1::2] = results[1::2] * self.crop_params[2] + self.crop_params[1]
            gesture=self.hk_gesture(results_show)
            results_show[0::2] = results_show[0::2] * (self.display_size[0] / self.rgb888p_size[0])
            results_show[1::2] = results_show[1::2] * (self.display_size[1] / self.rgb888p_size[1])
            return results_show,gesture

    def get_crop_param(self,det_box):
        x1, y1, x2, y2 = det_box[2],det_box[3],det_box[4],det_box[5]
        w,h= int(x2 - x1),int(y2 - y1)
        w_det = int(float(x2 - x1) * self.display_size[0] // self.rgb888p_size[0])
        h_det = int(float(y2 - y1) * self.display_size[1] // self.rgb888p_size[1])
        x_det = int(x1*self.display_size[0] // self.rgb888p_size[0])
        y_det = int(y1*self.display_size[1] // self.rgb888p_size[1])
        length = max(w, h)/2
        cx = (x1+x2)/2
        cy = (y1+y2)/2
        ratio_num = 1.26*length
        x1_kp = int(max(0,cx-ratio_num))
        y1_kp = int(max(0,cy-ratio_num))
        x2_kp = int(min(self.rgb888p_size[0]-1, cx+ratio_num))
        y2_kp = int(min(self.rgb888p_size[1]-1, cy+ratio_num))
        w_kp = int(x2_kp - x1_kp + 1)
        h_kp = int(y2_kp - y1_kp + 1)
        return [x1_kp, y1_kp, w_kp, h_kp]

    def hk_vector_2d_angle(self,v1,v2):
        with ScopedTiming("hk_vector_2d_angle",self.debug_mode > 0):
            v1_x,v1_y,v2_x,v2_y = v1[0],v1[1],v2[0],v2[1]
            v1_norm = np.sqrt(v1_x * v1_x+ v1_y * v1_y)
            v2_norm = np.sqrt(v2_x * v2_x + v2_y * v2_y)
            dot_product = v1_x * v2_x + v1_y * v2_y
            cos_angle = dot_product/(v1_norm*v2_norm)
            angle = np.acos(cos_angle)*180/np.pi
            return angle

    def hk_gesture(self,results):
        with ScopedTiming("hk_gesture",self.debug_mode > 0):
            angle_list = []
            for i in range(5):
                angle = self.hk_vector_2d_angle([(results[0]-results[i*8+4]), (results[1]-results[i*8+5])],[(results[i*8+6]-results[i*8+8]),(results[i*8+7]-results[i*8+9])])
                angle_list.append(angle)
            thr_angle,thr_angle_thumb,thr_angle_s,gesture_str = 65.,53.,49.,None
            if 65535. not in angle_list:
                if (angle_list[0]>thr_angle_thumb)  and (angle_list[1]>thr_angle) and (angle_list[2]>thr_angle) and (angle_list[3]>thr_angle) and (angle_list[4]>thr_angle):
                    gesture_str = "fist"
                elif (angle_list[0]<thr_angle_s)  and (angle_list[1]<thr_angle_s) and (angle_list[2]<thr_angle_s) and (angle_list[3]<thr_angle_s) and (angle_list[4]<thr_angle_s):
                    gesture_str = "five"
                elif (angle_list[0]<thr_angle_s)  and (angle_list[1]<thr_angle_s) and (angle_list[2]>thr_angle) and (angle_list[3]>thr_angle) and (angle_list[4]>thr_angle):
                    gesture_str = "gun"
                elif (angle_list[0]<thr_angle_s)  and (angle_list[1]<thr_angle_s) and (angle_list[2]>thr_angle) and (angle_list[3]>thr_angle) and (angle_list[4]<thr_angle_s):
                    gesture_str = "love"
                elif (angle_list[0]>5)  and (angle_list[1]<thr_angle_s) and (angle_list[2]>thr_angle) and (angle_list[3]>thr_angle) and (angle_list[4]>thr_angle):
                    gesture_str = "one"
                elif (angle_list[0]<thr_angle_s)  and (angle_list[1]>thr_angle) and (angle_list[2]>thr_angle) and (angle_list[3]>thr_angle) and (angle_list[4]<thr_angle_s):
                    gesture_str = "six"
                elif (angle_list[0]>thr_angle_thumb)  and (angle_list[1]<thr_angle_s) and (angle_list[2]<thr_angle_s) and (angle_list[3]<thr_angle_s) and (angle_list[4]>thr_angle):
                    gesture_str = "three"
                elif (angle_list[0]<thr_angle_s)  and (angle_list[1]>thr_angle) and (angle_list[2]>thr_angle) and (angle_list[3]>thr_angle) and (angle_list[4]>thr_angle):
                    gesture_str = "thumbUp"
                elif (angle_list[0]>thr_angle_thumb)  and (angle_list[1]<thr_angle_s) and (angle_list[2]<thr_angle_s) and (angle_list[3]>thr_angle) and (angle_list[4]>thr_angle):
                    gesture_str = "yeah"
            return gesture_str

class HandKeyPointClass:
    def __init__(self,hand_det_kmodel,hand_kp_kmodel,det_input_size,kp_input_size,labels,anchors,confidence_threshold=0.25,nms_threshold=0.3,nms_option=False,strides=[8,16,32],rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        self.hand_det_kmodel=hand_det_kmodel
        self.hand_kp_kmodel=hand_kp_kmodel
        self.det_input_size=det_input_size
        self.kp_input_size=kp_input_size
        self.labels=labels
        self.anchors=anchors
        self.confidence_threshold=confidence_threshold
        self.nms_threshold=nms_threshold
        self.nms_option=nms_option
        self.strides=strides
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        self.hand_det=HandDetApp(self.hand_det_kmodel,self.labels,model_input_size=self.det_input_size,anchors=self.anchors,confidence_threshold=self.confidence_threshold,nms_threshold=self.nms_threshold,nms_option=self.nms_option,strides=self.strides,rgb888p_size=self.rgb888p_size,display_size=self.display_size,debug_mode=0)
        self.hand_kp=HandKPClassApp(self.hand_kp_kmodel,model_input_size=self.kp_input_size,rgb888p_size=self.rgb888p_size,display_size=self.display_size)
        self.hand_det.config_preprocess()

    def run(self,input_np):
        det_boxes=self.hand_det.run(input_np)
        boxes=[]
        gesture_res=[]
        for det_box in det_boxes:
            x1, y1, x2, y2 = det_box[2],det_box[3],det_box[4],det_box[5]
            w,h= int(x2 - x1),int(y2 - y1)
            if (h<(0.1*self.rgb888p_size[1])):
                continue
            if (w<(0.25*self.rgb888p_size[0]) and ((x1<(0.03*self.rgb888p_size[0])) or (x2>(0.97*self.rgb888p_size[0])))):
                continue
            if (w<(0.15*self.rgb888p_size[0]) and ((x1<(0.01*self.rgb888p_size[0])) or (x2>(0.99*self.rgb888p_size[0])))):
                continue
            self.hand_kp.config_preprocess(det_box)
            results_show,gesture=self.hand_kp.run(input_np)
            gesture_res.append((results_show,gesture))
            boxes.append(det_box)
        return boxes,gesture_res

    def draw_result(self,pl,dets,gesture_res):
        pl.osd_img.clear()
        if len(dets)>0:
            for k in range(len(dets)):
                det_box=dets[k]
                x1, y1, x2, y2 = det_box[2],det_box[3],det_box[4],det_box[5]
                w,h= int(x2 - x1),int(y2 - y1)
                if (h<(0.1*self.rgb888p_size[1])):
                    continue
                if (w<(0.25*self.rgb888p_size[0]) and ((x1<(0.03*self.rgb888p_size[0])) or (x2>(0.97*self.rgb888p_size[0])))):
                    continue
                if (w<(0.15*self.rgb888p_size[0]) and ((x1<(0.01*self.rgb888p_size[0])) or (x2>(0.99*self.rgb888p_size[0])))):
                    continue
                w_det = int(float(x2 - x1) * self.display_size[0] // self.rgb888p_size[0])
                h_det = int(float(y2 - y1) * self.display_size[1] // self.rgb888p_size[1])
                x_det = int(x1*self.display_size[0] // self.rgb888p_size[0])
                y_det = int(y1*self.display_size[1] // self.rgb888p_size[1])
                pl.osd_img.draw_rectangle(x_det, y_det, w_det, h_det, color=(255, 0, 255, 0), thickness = 2)

                results_show=gesture_res[k][0]
                for i in range(len(results_show)//2):
                    pl.osd_img.draw_circle(results_show[i*2], results_show[i*2+1], 1, color=(255, 0, 255, 0),fill=False)
                for i in range(5):
                    j = i*8
                    if i==0:
                        R = 255; G = 0; B = 0
                    if i==1:
                        R = 255; G = 0; B = 255
                    if i==2:
                        R = 255; G = 255; B = 0
                    if i==3:
                        R = 0; G = 255; B = 0
                    if i==4:
                        R = 0; G = 0; B = 255
                    pl.osd_img.draw_line(results_show[0], results_show[1], results_show[j+2], results_show[j+3], color=(255,R,G,B), thickness = 3)
                    pl.osd_img.draw_line(results_show[j+2], results_show[j+3], results_show[j+4], results_show[j+5], color=(255,R,G,B), thickness = 3)
                    pl.osd_img.draw_line(results_show[j+4], results_show[j+5], results_show[j+6], results_show[j+7], color=(255,R,G,B), thickness = 3)
                    pl.osd_img.draw_line(results_show[j+6], results_show[j+7], results_show[j+8], results_show[j+9], color=(255,R,G,B), thickness = 3)

                gesture_str=gesture_res[k][1]
                pl.osd_img.draw_string_advanced( x_det , y_det-50,32, " " + str(gesture_str), color=(255,0, 255, 0))

# =========================================================================
# 低通滤波器
# =========================================================================
class LowPassFilter:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.value = None

    def update(self, new_val):
        if self.value is None:
            self.value = new_val
        else:
            self.value = self.alpha * new_val + (1.0 - self.alpha) * self.value
        return self.value

class RateLimiter:
    """
    速度限幅：每帧变化量超过 max_delta 的部分直接截断。
    噪声是突发跳变 → 被截断
    真实移动是渐变  → 正常跟随（包括夹着物体移动）
    不产生迟滞，也不阻止夹取中的位移。
    """
    def __init__(self, max_delta):
        self.max_delta = max_delta
        self.value     = None

    def update(self, new_val):
        if self.value is None:
            self.value = new_val
        else:
            delta = new_val - self.value
            if abs(delta) > self.max_delta:
                self.value += math.copysign(self.max_delta, delta)
            else:
                self.value = new_val
        return self.value

# =========================================================================
# 硬件物理常量
# =========================================================================
L1 = 135.0   # 大臂长度 (mm)
L2 = 147.0   # 小臂长度 (mm)
L3 =  65.0   # 手腕到夹爪中心补偿 (mm)

# =========================================================================
# 线性映射（带钳位保护）
# =========================================================================
def map_to_pulse(value, in_min, in_max, out_min, out_max):
    """
    线性映射 value 从 [in_min, in_max] 到 [out_min, out_max]。
    结果强制钳位在输出范围内，防止超限损坏舵机。
    """
    if in_max == in_min:
        return int(out_min)
    ratio  = (value - in_min) / (in_max - in_min)
    result = out_min + ratio * (out_max - out_min)
    lo, hi = (out_min, out_max) if out_min < out_max else (out_max, out_min)
    return int(max(lo, min(hi, result)))

# =========================================================================
# SO-ARM100 逆运动学：视觉空间坐标 → 六轴舵机脉冲
# =========================================================================
def spatial_to_arm(fx, fy, fz, froll, fgrip):
    """
    输入（均为低通滤波后的结果）：
      fx    : 水平比例 [0.0, 1.0]，0.5 为正中心
      fy    : 垂直比例 [0.0, 1.0]，0.0 最上，1.0 最下
      fz    : 视觉深度 [30.0, 180.0]，越小离摄像头越远
      froll : 手腕翻转角 [-90.0, 90.0] 度
      fgrip : 夹爪开合 [0.0, 1.0]，0.0 闭合，1.0 全开

    输出：(id1, id2, id3, id4, id5, id6) 六个整数脉冲值
    """

    # ------------------------------------------------------------------
    # 实际视觉检测范围（根据你的摄像头视角实测后在此修改）
    # ------------------------------------------------------------------
    FX_MIN, FX_MAX = 0.02, 0.30   # X 实际可检测范围
    FY_MIN, FY_MAX = 0.20, 0.40   # Y 实际可检测范围
    FZ_MIN, FZ_MAX = 40.0, 170.0  # Z 实际可检测范围（40=最远，170=最近）
    FX_MID = (FX_MIN + FX_MAX) / 2.0   # 0.16，作为底座旋转的中心

    # ------------------------------------------------------------------
    # Step 1：底座旋转 (ID1)
    # ------------------------------------------------------------------
    # 以实际检测范围的中点为零点，避免 dx 永远偏向一侧
    dx = fx - FX_MID
    norm_z = 1.0 - map_to_pulse(fz, FZ_MIN, FZ_MAX, 0, 800) / 1000.0
    dz = norm_z * 1.5
    theta_base_rad = math.atan2(dx, dz)
    theta_base_deg = theta_base_rad * 180.0 / math.pi
    id1 = map_to_pulse(theta_base_deg, -70.0, 70.0, 3315, 640)

    # ------------------------------------------------------------------
    # Step 2：空间笛卡尔映射与手腕解耦
    # ------------------------------------------------------------------
    # 用实际 Y 检测范围作为输入边界，让臂的全程对应手的全程
    Y_mm = map_to_pulse(fy, FY_MIN, FY_MAX, -100, 220) * 1.0

    # fz 越小=手越远=臂伸出，fz 越大=手越近=臂收回
    Z_target = map_to_pulse(fz, FZ_MIN, FZ_MAX, 280, 50) * 1.0

    # 减去手腕补偿，得到肘部目标点深度
    Z_wrist = Z_target - L3

    # ------------------------------------------------------------------
    # Step 3：两轴平面余弦逆运动学
    # ------------------------------------------------------------------
    D_sq = Y_mm * Y_mm + Z_wrist * Z_wrist
    D    = math.sqrt(D_sq)

    # 安全限位：目标超出最大臂展时按比例缩回
    max_reach = L1 + L2 - 1.0
    if D > max_reach:
        scale   = max_reach / D
        Y_mm   *= scale
        Z_wrist *= scale
        D        = max_reach
        D_sq     = D * D

    # 余弦定理求小臂内角
    cos_elbow = (D_sq - L1 * L1 - L2 * L2) / (2.0 * L1 * L2)
    cos_elbow = max(-1.0, min(1.0, cos_elbow))          # 防止浮点误差导致 acos 报错
    elbow_deg = math.acos(cos_elbow) * 180.0 / math.pi

    # 求大臂仰角
    alpha = math.atan2(Y_mm, Z_wrist)
    cos_beta = (D_sq + L1 * L1 - L2 * L2) / (2.0 * D * L1)
    cos_beta = max(-1.0, min(1.0, cos_beta))
    beta     = math.acos(cos_beta)
    shoulder_deg = (alpha + beta) * 180.0 / math.pi

    # ------------------------------------------------------------------
    # Step 4：手腕水平补偿
    # ------------------------------------------------------------------
    wrist_target_deg = 180.0 - shoulder_deg - elbow_deg

    # ------------------------------------------------------------------
    # Step 5：最终脉冲映射（基于实测标定点）
    # ------------------------------------------------------------------
    id2 = map_to_pulse(shoulder_deg,    0.0,  90.0,  333, 1372)  # 大臂
    id3 = map_to_pulse(elbow_deg,     180.0,  90.0,  875, 1871)  # 小臂
    id4 = map_to_pulse(wrist_target_deg, 0.0, 90.0, 2057, 3057)  # 手腕俯仰
    id5 = map_to_pulse(froll,         -90.0,  90.0,   82, 3926)  # 手腕旋转
    id6 = map_to_pulse(fgrip,           0.2,   1.0,  926, 2356)  # 夹爪（实测最小0.2）

    return id1, id2, id3, id4, id5, id6

# =========================================================================
# 空间坐标计算函数
# =========================================================================
def get_spatial_data(kp, img_width, img_height):
    """
    kp: 21个手部关键点坐标 [x0, y0, x1, y1, ...] (像素值)
    返回: (x, y, z, roll)
      x    -- 归一化水平坐标  0.0(左) ~ 1.0(右)
      y    -- 归一化垂直坐标  0.0(上) ~ 1.0(下)
      z    -- 加权手掌尺度，值越大代表手离镜头越近
      roll -- 手掌平面旋转角，单位度，范围 -180 ~ 180
    """
    # --- 1. 平面坐标 (x, y)，以掌心(点0)为参考 ---
    raw_x, raw_y = kp[0], kp[1]
    x = round(raw_x / img_width,  3)
    y = round(raw_y / img_height, 3)

    # --- 2. 深度值 (z) ---
    def dist(p1_idx, p2_idx):
        dx = kp[p1_idx * 2]     - kp[p2_idx * 2]
        dy = kp[p1_idx * 2 + 1] - kp[p2_idx * 2 + 1]
        return math.sqrt(dx * dx + dy * dy)

    d0_9  = dist(0,  9)   # 腕部  → 中指根部  (最稳定的手掌主轴)
    d5_17 = dist(5, 17)   # 食指根 → 小指根   (手掌横宽)
    d0_5  = dist(0,  5)   # 腕部  → 食指根部

    z_scale = (d0_9 * 0.5) + (d5_17 * 0.3) + (d0_5 * 0.2)
    z = round(z_scale, 2)

    # --- 3. 旋转角度 (Roll) ---
    idx_x, idx_y = kp[5  * 2], kp[5  * 2 + 1]
    pnk_x, pnk_y = kp[17 * 2], kp[17 * 2 + 1]
    angle_rad = math.atan2(pnk_y - idx_y, pnk_x - idx_x)
    roll = round(angle_rad * 180 / math.pi, 1)

    # --- 4. 夹爪开合度 (grip) ---
    # 拇指尖(点4) 到 食指尖(点8) 的距离，除以手掌尺度归一化
    # 结果 0.0 = 完全捏合，1.0 = 完全张开
    d4_8 = dist(4, 8)
    # z_scale 作为参考尺度，捏合时约0，张开时约与手掌等宽
    grip_raw = d4_8 / z_scale if z_scale > 0 else 0.0
    # 典型范围约 0.0~0.8，映射并钳位到 0.0~1.0
    grip = round(max(0.0, min(1.0, grip_raw / 0.8)), 3)

    return x, y, z, roll, grip

# =========================================================================
# 以下是主函数部分 (包含串口初始化和数据发送逻辑)
# =========================================================================

if __name__=="__main__":
    # 显示模式，默认"hdmi",可以选择"hdmi"和"lcd"
    display_mode="lcd"
    # k230保持不变，k230d可调整为[640,360]
    rgb888p_size = [1920, 1080]

    if display_mode=="hdmi":
        display_size=[1920,1080]
    else:
        display_size=[800,480]
    # 手掌检测模型路径
    hand_det_kmodel_path="/sdcard/examples/kmodel/hand_det.kmodel"
    # 手掌关键点模型路径
    hand_kp_kmodel_path="/sdcard/examples/kmodel/handkp_det.kmodel"
    # 其他参数
    anchors_path="/sdcard/examples/utils/prior_data_320.bin"
    hand_det_input_size=[512,512]
    hand_kp_input_size=[256,256]
    confidence_threshold=0.2
    nms_threshold=0.5
    labels=["hand"]
    anchors = [26,27, 53,52, 75,71, 80,99, 106,82, 99,134, 140,113, 161,172, 245,276]

    # 初始化PipeLine
    pl=PipeLine(rgb888p_size=rgb888p_size,display_size=display_size,display_mode=display_mode)
    pl.create()
    hkc=HandKeyPointClass(hand_det_kmodel_path,hand_kp_kmodel_path,det_input_size=hand_det_input_size,kp_input_size=hand_kp_input_size,labels=labels,anchors=anchors,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,nms_option=False,strides=[8,16,32],rgb888p_size=rgb888p_size,display_size=display_size)

    # 🌟 组长配置：初始化串口，准备给 MCU 发数据
    fpioa = FPIOA()
    fpioa.set_function(5, FPIOA.UART2_TXD)
    fpioa.set_function(6, FPIOA.UART2_RXD)
    uart = UART(UART.UART2, baudrate=1000000, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
    print("AI 模型加载完成，串口已准备好！")

    # 🌟 初始化四路低通滤波器（每个维度独立一个）
    lpf_x    = LowPassFilter(alpha=0.2)
    lpf_y    = LowPassFilter(alpha=0.2)
    lpf_grip = LowPassFilter(alpha=0.2)
    # Z 和 Roll：先限速截断突变，再低通平滑
    rl_z     = RateLimiter(max_delta=8.0)    # Z 每帧最多变化 8px
    lpf_z    = LowPassFilter(alpha=0.3)
    rl_roll  = RateLimiter(max_delta=6.0)    # Roll 每帧最多变化 6°
    lpf_roll = LowPassFilter(alpha=0.3)
    fz    = None
    froll = None

    try:
        while True:
            os.exitpoint()
            with ScopedTiming("total",1):
                img=pl.get_frame()                          # 获取当前帧
                det_boxes,gesture_res=hkc.run(img)          # 推理当前帧
                hkc.draw_result(pl,det_boxes,gesture_res)   # 绘制当前帧推理结果

                # 🌟 提取手势 + 空间坐标 → 滤波 → 打印
                if len(gesture_res) > 0:
                    kp          = gesture_res[0][0]
                    gesture_str = gesture_res[0][1]

                    # --- 1. 计算原始空间坐标 ---
                    curr_x, curr_y, curr_z, curr_roll, curr_grip = get_spatial_data(
                        kp, rgb888p_size[0], rgb888p_size[1]
                    )

                    # --- 2. 低通滤波 ---
                    # 握拳时 Z 和 Roll 不可信，冻结上一帧稳定值，只更新 X/Y/Grip
                    fx    = lpf_x.update(curr_x)
                    fy    = lpf_y.update(curr_y)
                    fgrip = lpf_grip.update(curr_grip)
                    fz    = lpf_z.update(rl_z.update(curr_z))
                    froll = lpf_roll.update(rl_roll.update(curr_roll))

                    # --- 3. IK 解算 + 打印 + 串口发送 ---
                    if fz is not None and froll is not None:
                        id1, id2, id3, id4, id5, id6 = spatial_to_arm(fx, fy, fz, froll, fgrip)
                        print(f"X:{round(fx,3)} Y:{round(fy,3)} Z:{round(fz,2)} Roll:{round(froll,1)}° Grip:{round(fgrip,3)}")
                        print(f"PWM -> {id1},{id2},{id3},{id4},{id5},{id6}")
                        # 格式: "id1,id2,id3,id4,id5,id6\n"，MCU 直接驱动舵机
                        send_data = f"{id1},{id2},{id3},{id4},{id5},{id6}\n"
                        uart.write(send_data.encode('utf-8'))

                pl.show_image()                             # 展示推理结果
                gc.collect()
    except Exception as e:
        sys.print_exception(e)
    finally:
        hkc.hand_det.deinit()
        hkc.hand_kp.deinit()
        pl.destroy()
        uart.deinit() # 🌟 别忘了最后释放串口资源
