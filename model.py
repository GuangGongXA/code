from __future__ import print_function

import os
import time
import random
from utils import data_augmentation
from PIL import Image
import tensorflow as tf
import numpy as np
import tensorflow.contrib.slim as slim
from utils import *

def concat(layers):
    return tf.concat(layers, axis=3)

def mutual_i_input_loss(input_I_low, input_im):
    input_gray = tf.image.rgb_to_grayscale(input_im)
    low_gradient_x = gradient(input_I_low, "x")
    input_gradient_x = gradient(input_gray, "x")
    x_loss = tf.abs(tf.div(low_gradient_x, tf.maximum(input_gradient_x, 0.01)))
    low_gradient_y = gradient(input_I_low, "y")
    input_gradient_y = gradient(input_gray, "y")
    y_loss = tf.abs(tf.div(low_gradient_y, tf.maximum(input_gradient_y, 0.01)))
    mut_loss = tf.reduce_mean(x_loss + y_loss) 
    return mut_loss


def gradient(input_tensor, direction):
    smooth_kernel_x = tf.reshape(tf.constant([[0, 0], [-1, 1]], tf.float32), [2, 2, 1, 1])
    smooth_kernel_y = tf.transpose(smooth_kernel_x, [1, 0, 2, 3])
    if direction == "x":
        kernel = smooth_kernel_x
    elif direction == "y":
        kernel = smooth_kernel_y
    gradient_orig = tf.abs(tf.nn.conv2d(input_tensor, kernel, strides=[1, 1, 1, 1], padding='SAME'))
    grad_min = tf.reduce_min(gradient_orig)
    grad_max = tf.reduce_max(gradient_orig)
    grad_norm = tf.div((gradient_orig - grad_min), (grad_max - grad_min + 0.0001))
    return grad_norm


def at(x):
    pool1 = tf.layers.average_pooling2d(x, pool_size=[3, 3], strides=1, padding='same')
    pool2 = tf.layers.max_pooling2d(x, pool_size=[3, 3], strides=1, padding='same')
    c1 = slim.conv2d(pool1, 32, 3, padding='same', activation_fn=tf.nn.relu)
    c2 = slim.conv2d(pool2, 32, 3, padding='same', activation_fn=tf.nn.relu)
    conv1 = slim.conv2d(c1, 64, 3, padding='same', activation_fn=None) 
    conv2 = slim.conv2d(c2, 64, 3, padding='same', activation_fn=None) 
    attention = tf.sigmoid(conv1 + conv2)
    return attention

    
def DecomNet(input_im, layer_num, channel=64, kernel_size=3):
    input_max = tf.reduce_max(input_im, axis=3, keepdims=True)
    input_im = concat([input_max, input_im])
    with tf.variable_scope('DecomNet', reuse=tf.AUTO_REUSE):
        conv = slim.conv2d(input_im, channel, kernel_size * 3, padding='same', activation_fn=tf.nn.relu)
        for idx in range(layer_num):
            conv1 = slim.conv2d(conv, channel, kernel_size, padding='same', activation_fn=None)
            conv = slim.conv2d(conv1, channel, kernel_size, padding='same', activation_fn=tf.nn.relu)
           
        conv = slim.conv2d(conv, 4, kernel_size, padding='same', activation_fn=None)

    R = tf.sigmoid(conv[:,:,:,0:3])
    L = tf.sigmoid(conv[:,:,:,3:4])

    return R, L



def RelightNet(input_L, input_R, channel=64, kernel_size=3):
    # input_im = concat([input_R, input_L])
    with tf.variable_scope('RelightNet'):
        conv0 = slim.conv2d(input_L, channel, kernel_size, padding='same', activation_fn=None)#48*48
        attention1 = at(conv0)

        conv1 = tf.layers.conv2d(conv0, channel, kernel_size, strides=2, padding='same', activation=tf.nn.relu)     #48*48
        attention2 = at(conv1)     
        
        conv2 = tf.layers.conv2d(conv1, channel, kernel_size, strides=2, padding='same', activation=tf.nn.relu) #24*24
        attention3 = at(conv2)       
               
        conv3 = tf.layers.conv2d(conv2, channel, kernel_size, strides=2, padding='same', activation=tf.nn.relu) #12*12
        attention4 = at(conv3)   
        
        conv4 = tf.layers.conv2d(conv3, channel, kernel_size, strides=2, padding='same', activation=tf.nn.relu) #6*6
        attention5 = at(conv4)
        
        conv5 = tf.layers.conv2d(conv4, channel, kernel_size, strides=2, padding='same', activation=tf.nn.relu)     #3*3
            
        up1 = tf.image.resize_nearest_neighbor(conv5, (tf.shape(conv4)[1], tf.shape(conv4)[2]))
        deconv1 = slim.conv2d(up1, channel, kernel_size, 1, padding='same', activation_fn=tf.nn.relu) * attention5 + conv4
        up2 = tf.image.resize_nearest_neighbor(deconv1, (tf.shape(conv3)[1], tf.shape(conv3)[2]))        
        deconv2= slim.conv2d(up2, channel, kernel_size, 1, padding='same', activation_fn=tf.nn.relu) * attention4 + conv3
        up3 = tf.image.resize_nearest_neighbor(deconv2, (tf.shape(conv2)[1], tf.shape(conv2)[2]))
        deconv3 = slim.conv2d(up3, channel, kernel_size, 1, padding='same', activation_fn=tf.nn.relu) * attention3 + conv2
        up4 = tf.image.resize_nearest_neighbor(deconv3, (tf.shape(conv1)[1], tf.shape(conv1)[2]))
        deconv4 = slim.conv2d(up4, channel, kernel_size, 1, padding='same', activation_fn=tf.nn.relu) * attention2 + conv1
        up5 = tf.image.resize_nearest_neighbor(deconv4, (tf.shape(conv0)[1], tf.shape(conv0)[2]))
        deconv5 = slim.conv2d(up5, channel, kernel_size, 1, padding='same', activation_fn=tf.nn.relu) * attention1 + conv0
        
        deconv1_resize = tf.image.resize_nearest_neighbor(deconv1, (tf.shape(deconv5)[1], tf.shape(deconv5)[2]))
        deconv2_resize = tf.image.resize_nearest_neighbor(deconv2, (tf.shape(deconv5)[1], tf.shape(deconv5)[2]))
        deconv3_resize = tf.image.resize_nearest_neighbor(deconv3, (tf.shape(deconv5)[1], tf.shape(deconv5)[2]))
        deconv4_resize = tf.image.resize_nearest_neighbor(deconv4, (tf.shape(deconv5)[1], tf.shape(deconv5)[2]))
        feature_gather = tf.concat([deconv1_resize,deconv2_resize, deconv3_resize, deconv4_resize, deconv5], axis=3)
        feature_fusion = slim.conv2d(feature_gather, channel, 1, padding='same', activation_fn=None)

        output = slim.conv2d(feature_fusion, 1, 3, padding='same', activation_fn=None)
        return output

        

def Discriminator(x): 
    with tf.variable_scope('Discriminator', reuse=tf.AUTO_REUSE):
        c = slim.conv2d(x, 32, 3, padding='same', activation_fn=tf.nn.relu)
        c0 = slim.conv2d(c, 32, 3, padding='same', activation_fn=tf.nn.relu)     
        c1 = tf.layers.conv2d(c0, 64, 3, padding='same', activation = tf.nn.relu)
        c2 = tf.layers.conv2d(c1, 64, 3, padding='same', activation = tf.nn.relu)
        c3 = tf.layers.conv2d(c2, 64, 3, padding='same', activation = tf.nn.relu)
        c4 = tf.layers.conv2d(c3, 64, 3, padding='same', activation = None)
        c5 = c3 * c4
        c5 = tf.layers.conv2d(c4, 64, 3, padding='same', activation = tf.nn.relu)
        c6 = tf.layers.conv2d(c5, 64, 3, padding='same', activation = tf.nn.relu)
#   
        D_logit = tf.layers.dense(c6, 128, tf.nn.relu)
        D_prob = tf.layers.dense(D_logit, 1, tf.nn.sigmoid) 
        

    return D_prob, D_logit


class lowlight_enhance(object):
    def __init__(self, sess):
        self.sess = sess
        self.DecomNet_layer_num = 6
        ##学习率
        self.learning_rate = 0.0001
        self.beta1 = 0.5
        self.disc_iters = 1
        self.lambd = 0.00005 
  
        # build the model
        self.input_low = tf.placeholder(tf.float32, [None, None, None, 3], name='input_low')
        self.input_high = tf.placeholder(tf.float32, [None, None, None, 3], name='input_high')

        [R_low, I_low] = DecomNet(self.input_low, self.DecomNet_layer_num)
        [R_high, I_high] = DecomNet(self.input_high, self.DecomNet_layer_num)
        
        I_delta = RelightNet(I_low, R_low)  

        I_low_3 = concat([I_low, I_low, I_low])
        I_high_3 = concat([I_high, I_high, I_high])
        I_delta_3 = concat([I_delta, I_delta, I_delta])

        self.output_R_low = R_low
        self.output_I_low = I_low_3
        self.output_I_delta = I_delta_3
        self.output_S = R_low * I_delta_3
        self.I_high = I_high_3

        # loss
        self.recon_loss_low = tf.reduce_mean(tf.abs(R_low * I_low_3 -  self.input_low))
        self.recon_loss_high = tf.reduce_mean(tf.abs(R_high * I_high_3 - self.input_high))
        self.recon_loss_mutal_low = tf.reduce_mean(tf.abs(R_high * I_low_3 - self.input_low))
        self.recon_loss_mutal_high = tf.reduce_mean(tf.abs(R_low * I_high_3 - self.input_high))
        self.equal_R_loss = tf.reduce_mean(tf.abs(R_low - R_high))  
        self.relight_loss = tf.reduce_mean(tf.abs((R_low * I_delta_3 - self.input_high))) #* [[[[0.11448, 0.58661, 0.29891]]]]))#tf.reduce_mean(tf.abs(R_low * I_delta_3 - self.input_high))
   
        i_input_mutual_loss_high = mutual_i_input_loss(I_high, self.input_high)
        i_input_mutual_loss_low = mutual_i_input_loss(I_low, self.input_low)
     
        self.Ismooth_loss_low = self.smooth(I_low, R_low)
        self.Ismooth_loss_high = self.smooth(I_high, R_high)
        self.Ismooth_loss_delta = self.smooth(I_delta, R_low)

        self.loss_Decom = self.recon_loss_low + self.recon_loss_high + 0.01 * self.equal_R_loss + 0.15* i_input_mutual_loss_high + 0.15* i_input_mutual_loss_low + 0.001*self.recon_loss_mutal_low +  0.001*self.recon_loss_mutal_high + 0.1 * self.Ismooth_loss_low + 0.1 * self.Ismooth_loss_high
        
        _, self.D_real_logits = Discriminator(self.input_high)
        _, self.D_fake_logits = Discriminator(R_low * I_delta_3)

        self.D_loss_real = - tf.reduce_mean(self.D_real_logits)
        self.D_loss_fake = tf.reduce_mean(self.D_fake_logits)

        self.G_loss_I = -self.D_loss_fake

        self.D_loss = self.D_loss_fake + self.D_loss_real 
        
        self.loss_Relight = self.relight_loss

        """ Gradient Penalty """
        alpha = tf.random_uniform(shape=(3, ), minval=0.,maxval=1.)
        differences = R_low * I_delta_3 - self.input_high 
        interpolates = self.input_high + (alpha * differences)
        _, D_inter = Discriminator(interpolates)
        gradients = tf.gradients(D_inter, [interpolates])[0]
        slopes = tf.sqrt(tf.reduce_sum(tf.square(gradients), reduction_indices=[1]))
        gradient_penalty = tf.reduce_mean((slopes - 1.) ** 2)
        self.D_loss += self.lambd * gradient_penalty
        
        self.lr = tf.placeholder(tf.float32, name='learning_rate')
        optimizer = tf.train.AdamOptimizer(self.lr, name='AdamOptimizer')

        self.var_Decom = [var for var in tf.trainable_variables() if 'DecomNet' in var.name]
        
        self.var_Relight = [var for var in tf.trainable_variables() if 'RelightNet' in var.name]
        
        t_vars = tf.trainable_variables()
        d_vars = [var for var in t_vars if 'd_' in var.name]
        self.clip_D = [p.assign(tf.clip_by_value(p, -0.01, 0.01)) for p in d_vars]
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            self.train_op_D_Loss= tf.train.AdamOptimizer(self.lr, beta1=self.beta1).minimize(self.D_loss, var_list=d_vars)
            self.train_op_G_Loss_I= tf.train.AdamOptimizer(self.lr, beta1=self.beta1).minimize(self.G_loss_I, var_list=d_vars)
             
        self.train_op_Decom = optimizer.minimize(self.loss_Decom, var_list = self.var_Decom)
        self.train_op_Relight = optimizer.minimize(self.loss_Relight, var_list = self.var_Relight) 

        self.D_loss_real_sum = tf.summary.scalar("D_loss_real", self.D_loss_real)
        self.D_loss_fake_sum = tf.summary.scalar("D_loss_fake", self.D_loss_fake)
        self.D_loss_sum = tf.summary.scalar("D_loss", self.D_loss)
        self.G_loss_sum = tf.summary.scalar("G_loss", self.loss_Relight)

        # final summary operations
        self.G_sum = tf.summary.merge([self.D_loss_fake_sum, self.G_loss_sum])
        self.D_sum = tf.summary.merge([self.D_loss_real_sum, self.D_loss_sum])
        
        self.sess.run(tf.global_variables_initializer())

        self.saver_Decom = tf.train.Saver(var_list = self.var_Decom)
        self.saver_Relight = tf.train.Saver(var_list = self.var_Relight)

        ###D
        print("[*] Initialize model successfully...")

    def gradient(self, input_tensor, direction):
        self.smooth_kernel_x = tf.reshape(tf.constant([[0, 0], [-1, 1]], tf.float32), [2, 2, 1, 1])
        self.smooth_kernel_y = tf.transpose(self.smooth_kernel_x, [1, 0, 2, 3])

        if direction == "x":
            kernel = self.smooth_kernel_x
        elif direction == "y":
            kernel = self.smooth_kernel_y
        return tf.abs(tf.nn.conv2d(input_tensor, kernel, strides=[1, 1, 1, 1], padding='SAME'))

    def ave_gradient(self, input_tensor, direction):
        return tf.layers.average_pooling2d(self.gradient(input_tensor, direction), pool_size=3, strides=1, padding='SAME')

    def smooth(self, input_I, input_R):
        input_R = tf.image.rgb_to_grayscale(input_R)
        return tf.reduce_mean(self.gradient(input_I, "x") * tf.exp(-10 * self.ave_gradient(input_R, "x")) + self.gradient(input_I, "y") * tf.exp(-10 * self.ave_gradient(input_R, "y")))

    def evaluate(self, epoch_num, eval_low_data, sample_dir, train_phase):
        print("[*] Evaluating for phase %s / epoch %d..." % (train_phase, epoch_num))

        for idx in range(len(eval_low_data)):
            input_low_eval = np.expand_dims(eval_low_data[idx], axis=0)

            if train_phase == "Decom":
                result_1, result_2 = self.sess.run([self.output_R_low, self.output_I_low], feed_dict={self.input_low: input_low_eval})
                save_images(os.path.join(sample_dir, 'eval_%s_%d_%d.png' % (train_phase, idx + 1, epoch_num)), result_1, result_2)
            if train_phase == "Relight":
                result_3, result_4 = self.sess.run([self.output_S, self.output_I_delta], feed_dict={self.input_low: input_low_eval})
                save_images(os.path.join(sample_dir, 'eval_%s_%d_%d.png' % (train_phase, idx + 1, epoch_num)), result_3, result_4)
            

    def train(self, train_low_data, train_high_data, eval_low_data, batch_size, patch_size, epoch, lr, sample_dir, ckpt_dir, eval_every_epoch, train_phase):
        assert len(train_low_data) == len(train_high_data)
        numBatch = len(train_low_data) // int(batch_size)

        # load pretrained model
        if train_phase == "Decom":
            train_op = self.train_op_Decom
            train_loss = self.loss_Decom
            saver = self.saver_Decom      
            load_model_status, global_step = self.load(saver, ckpt_dir)
            if load_model_status:
                iter_num = global_step
                start_epoch = global_step // numBatch
                start_step = global_step % numBatch
                print("[*] Model restore success!")
            else:
                iter_num = 0
                start_epoch = 0
                start_step = 0
                print("[*] Not find pretrained model!")

            print("[*] Start training for phase %s, with start epoch %d start iter %d : " % (train_phase, start_epoch, iter_num))

            start_time = time.time()
            image_id = 0

            for epoch in range(start_epoch, epoch):
                for batch_id in range(start_step, numBatch):
                # generate data for a batch
                    batch_input_low = np.zeros((batch_size, patch_size, patch_size, 3), dtype="float32")
                    batch_input_high = np.zeros((batch_size, patch_size, patch_size, 3), dtype="float32")
                    for patch_id in range(batch_size):
                        h, w, _ = train_low_data[image_id].shape
                        x = random.randint(0, h - patch_size)
                        y = random.randint(0, w - patch_size)
            
                        rand_mode = random.randint(0, 7)
                        batch_input_low[patch_id, :, :, :] = data_augmentation(train_low_data[image_id][x : x+patch_size, y : y+patch_size, :], rand_mode)
                        batch_input_high[patch_id, :, :, :] = data_augmentation(train_high_data[image_id][x : x+patch_size, y : y+patch_size, :], rand_mode)
                    
                        image_id = (image_id + 1) % len(train_low_data)
                        if image_id == 0:
                            tmp = list(zip(train_low_data, train_high_data))
                            random.shuffle(list(tmp))
                            train_low_data, train_high_data  = zip(*tmp)
                # train
               
                    _, loss = self.sess.run([train_op, train_loss], feed_dict={self.input_low: batch_input_low, \
                                                                           self.input_high: batch_input_high, \
                                                                           self.lr: lr[epoch]})
                    print("%s Epoch: [%2d] [%4d/%4d] time: %4.4f, loss: %.6f" \
                          % (train_phase, epoch + 1, batch_id + 1, numBatch, time.time() - start_time, loss))
                    iter_num += 1

            # evalutate the model and save a checkpoint file for it
                if (epoch + 1) % eval_every_epoch == 0:
                    self.evaluate(epoch + 1, eval_low_data, sample_dir=sample_dir, train_phase=train_phase)
                    self.save(saver, iter_num, ckpt_dir, "RetinexNet-%s" % train_phase)

            print("[*] Finish training for phase %s." % train_phase)


        if train_phase == "Relight":
            saver = self.saver_Relight
            
            #load_model_status,  global_step = self.load(self.checkpoint_dir)
            load_model_status, global_step = self.load(saver, ckpt_dir)
            if load_model_status:
                iter_num = global_step
                start_epoch = global_step // numBatch
                start_step = global_step % numBatch
                
                print("[*] Model restore success!")
            else:
                iter_num = 0
                start_epoch = 0
                start_step = 0
                print("[*] Not find pretrained model!")

            print("[*] Start training for phase %s, with start epoch %d start iter %d : " % (train_phase, start_epoch, iter_num))

            start_time = time.time()
            image_id = 0
            for epoch in range(start_epoch, epoch):
                for batch_id in range(start_step, numBatch):
                    batch_input_low = np.zeros((batch_size, patch_size, patch_size, 3), dtype="float32")
                    batch_input_high = np.zeros((batch_size, patch_size, patch_size, 3), dtype="float32")
                    for patch_id in range(batch_size):
                        h, w, _ = train_low_data[image_id].shape
                        x = random.randint(0, h - patch_size)
                        y = random.randint(0, w - patch_size)
            
                        rand_mode = random.randint(0, 7)
                        batch_input_low[patch_id, :, :, :] = data_augmentation(train_low_data[image_id][x : x+patch_size, y : y+patch_size, :], rand_mode)
                        batch_input_high[patch_id, :, :, :] = data_augmentation(train_high_data[image_id][x : x+patch_size, y : y+patch_size, :], rand_mode)
                    
                        image_id = (image_id + 1) % len(train_low_data)
                        if image_id == 0:
                            tmp = list(zip(train_low_data, train_high_data))
                            random.shuffle(list(tmp))
                            train_low_data, train_high_data  = zip(*tmp)
                            
                    _, _, summary_str, D_loss = self.sess.run([self.train_op_D_Loss, self.clip_D, self.D_sum, self.D_loss],
                                              feed_dict={self.input_low:batch_input_low ,\
                                              self.input_high: batch_input_high, \
                                              self.lr: lr[epoch]})
                    
                    if iter_num % self.disc_iters == 0:
                        _, summary_str,G_loss_I, _, loss_Relight = self.sess.run([self.train_op_G_Loss_I, self.G_sum,self.G_loss_I ,\
                                                                self.train_op_Relight, self.loss_Relight], 
                                                               feed_dict={self.input_low: batch_input_low, \
                                                               self.input_high: batch_input_high,\
                                                               self.lr: lr[epoch]})
                        
                       
                    iter_num += 1
                    print("%s Epoch: [%2d] [%4d/%4d] time: %4.4f, D_loss: %.6f, G_loss_I: %.6f, loss_Religh: %.6f" \
                          % (train_phase, epoch + 1, batch_id + 1, numBatch, time.time() - start_time, D_loss, G_loss_I, loss_Relight))
                    
                start_epoch = 0
                if (epoch + 1) % eval_every_epoch == 0:
                    self.evaluate(epoch + 1, eval_low_data, sample_dir=sample_dir, train_phase=train_phase)
                    self.save(saver, iter_num, ckpt_dir, "RetinexNet-%s" % train_phase)
                # save model
                
            print("[*] Finish training for phase %s." % train_phase)
                # show temporal results

    def save(self, saver, iter_num, ckpt_dir, model_name):
        if not os.path.exists(ckpt_dir):
            os.makedirs(ckpt_dir)
        print("[*] Saving model %s" % model_name)
        saver.save(self.sess, \
                   os.path.join(ckpt_dir, model_name), \
                   global_step=iter_num)

    def load(self, saver, ckpt_dir):
        ckpt = tf.train.get_checkpoint_state(ckpt_dir)
        if ckpt and ckpt.model_checkpoint_path:
            full_path = tf.train.latest_checkpoint(ckpt_dir)
            try:
                global_step = int(full_path.split('/')[-1].split('-')[-1])
            except ValueError:
                global_step = None
            saver.restore(self.sess, full_path)
            return True, global_step
        else:
            print("[*] Failed to load model from %s" % ckpt_dir)
            return False, 0

    def test(self, test_low_data, test_high_data, test_low_data_names, save_dir, decom_flag):
        tf.global_variables_initializer().run()

        print("[*] Reading checkpoint...")
      
        load_model_status_Decom, _ = self.load(self.saver_Decom, './checkpoint/Decom')
        load_model_status_Relight, _ = self.load(self.saver_Relight, './checkpoint/Relight')

        if load_model_status_Decom and load_model_status_Relight:
            print("[*] Load weights successfully...")
        
        print("[*] Testing...")
        for idx in range(len(test_low_data)):
            print(test_low_data_names[idx])
            [_, name] = os.path.split(test_low_data_names[idx])
            suffix = name[name.find('.') + 1:]
            name = name[:name.find('.')]

            input_low_test = np.expand_dims(test_low_data[idx], axis=0)
            [R_low, I_low, I_delta, S] = self.sess.run([self.output_R_low, self.output_I_low, self.output_I_delta, self.output_S], feed_dict = {self.input_low: input_low_test})
            
            if decom_flag == 1:
                save_images(os.path.join(save_dir, name + "_S." + suffix), S)

            save_images(os.path.join(save_dir, name + "_S."   + suffix), S)




     