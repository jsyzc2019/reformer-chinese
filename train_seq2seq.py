import transformers
import torch
import os
import json
import random
import numpy as np
import argparse
# from torch.utils.tensorboard import SummaryWriter
from datetime import datetime
from tqdm import tqdm
from torch.nn import DataParallel
# from tokenizations.bpe_tokenizer import get_encoder
# import pre_process_data as ppd
import pickle
from transformers import *
import torch
import os
from torch import randint
import torch.nn as nn
# from reformer_pytorch import ReformerLM
from reformer_pytorch import ReformerEncDec
from reformer_pytorch.generative_tools import TrainingWrapper
from reformer_chinese import *
import tkitJson
import shutil
import math

from db import DB
def build_files(data_path, tokenized_data_path, num_pieces, full_tokenizer, max_length_input,max_length_output):
    print(data_path)
    Tjson=tkitJson.Json(data_path)
    lines=[]
    for item in Tjson.load():
        # print(item['sentenceA'])

        # print(full_tokenizer.encode_plus(item['sentenceA'],max_length=max_length,pad_to_max_length=True))
        sentA_ids=full_tokenizer.encode_plus(item['sentenceA'],max_length=max_length_input,pad_to_max_length=True)['input_ids']
        sentB_ids=full_tokenizer.encode_plus(item['sentenceB'],max_length=max_length_output,pad_to_max_length=True)['input_ids']
        yield sentA_ids,sentB_ids

def auto_encode(sentence_0,tokenizer):
  # sentence_1 = "我是谁啊"
  sentence_1=None
  inputs_1 = tokenizer.encode_plus(sentence_0, sentence_1, add_special_tokens=True, return_tensors='pt')
  return inputs_1['input_ids']
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='cuda', type=str, required=False, help='设置使用哪些显卡')
    # parser.add_argument('--model_config', default='config/model_config_small.json', type=str, required=False,
    #                     help='选择模型参数')
    parser.add_argument('--tokenizer_path', default='cache/vocab_small_terry_ai.txt', type=str, required=False, help='选择词库')
    parser.add_argument('--raw_data_path', default='data/train.json', type=str, required=False, help='原始训练语料')
    parser.add_argument('--raw_only', action="store_true", help="只进行数据预处理")
    parser.add_argument('--tokenized_data_path', default='data/tokenized/', type=str, required=False,
                        help='tokenized语料存放位置')
    parser.add_argument('--raw', action='store_true', help='是否先做tokenize')
    parser.add_argument('--epochs', default=5, type=int, required=False, help='训练循环')
    parser.add_argument('--batch_size', default=2, type=int, required=False, help='训练batch size')
    parser.add_argument('--lr', default=1e-8, type=float, required=False, help='学习率')
    parser.add_argument('--warmup_steps', default=200, type=int, required=False, help='warm up步数')
    parser.add_argument('--log_step', default=1, type=int, required=False, help='多少步汇报一次loss')
    parser.add_argument('--max_data',default=0,type=int, required=False, help='输入限制的最多数据集量')
    parser.add_argument('--stride', default=500, type=int, required=False, help=' 向前跨越的长度')
    parser.add_argument('--dim', default=128, type=int, required=False, help='训练时取训练数据的窗口步长单个样本长度')
    parser.add_argument('--gradient_accumulation', default=5, type=int, required=False, help='梯度积累')
    parser.add_argument('--fp16', action='store_true', help='混合精度')
    parser.add_argument('--fp16_opt_level', default='O1', type=str, required=False)
    parser.add_argument('--max_grad_norm', default=1.0, type=float, required=False)
    parser.add_argument('--num_pieces', default=10, type=int, required=False, help='将训练语料分成多少份')
    parser.add_argument('--min_length', default=64, type=int, required=False, help='最短收录文章长度')
    parser.add_argument('--output_dir', default='model/', type=str, required=False, help='模型输出路径')
    parser.add_argument('--pretrained_model', default='', type=str, required=False, help='模型训练起点路径')
    # parser.add_argument('--writer_dir', default='tensorboard_summary/', type=str, required=False, help='Tensorboard路径')
    parser.add_argument('--segment', action='store_true', help='中文以词为单位')
    parser.add_argument('--bpe_token', action='store_true', help='subword')
    parser.add_argument('--enc_depth',default=6, type=int, help="enc_depth")
    parser.add_argument('--dec_depth',default=6, type=int, help="dec_depth")
    # parser.add_argument('--dim', default=1024, type=int, required=False, help='dim')
    parser.add_argument('--depth', default=12, type=int, required=False, help='depth')
    parser.add_argument('--full_attn_thres', default=1024, type=int, required=False, help='full_attn_thres')
    parser.add_argument('--max_seq_len', default=4096, type=int, required=False, help='max_seq_len')
    # parser.add_argument('--encoder_json', default="tokenizations/encoder.json", type=str, help="encoder.json")
    # parser.add_argument('--vocab_bpe', default="tokenizations/vocab.bpe", type=str, help="vocab.bpe")
    parser.add_argument('--db_loss', action='store_true', help='是否是对loss追踪')
    parser.add_argument('--password',type=str,help="远程数据库密码")
    args = parser.parse_args()
    full_tokenizer=tokenizer_plus(args.tokenizer_path)
    config_file=os.path.join(args.output_dir,'config.json')
    Config=tkitJson.Config(config_file)
    new_conf={'num_tokens':full_tokenizer.vocab_size,
    'dim': args.dim, #和窗口长度一样 
    'depth' : args.depth,
    'max_seq_len' :  args.max_seq_len,
    'lsh_dropout' : 0.1,
    'causal' : True,
    'full_attn_thres' : args.full_attn_thres,
    'stride': args.stride,  #滑块长度
    }
    print("new_conf:",new_conf)
    Config.save(new_conf)
    #复制词典
    shutil.copy(args.tokenizer_path,os.path.join(args.output_dir,'vocab.txt'))
    
    print('args:\n' + args.__repr__())

    # if args.segment:
    #     from tokenizations import tokenization_bert_word_level as tokenization_bert
    # else:
    #     from tokenizations import tokenization_bert

    os.environ["CUDA_VISIBLE_DEVICES"] = '0,1,2,3' # 此处设置程序使用哪些显卡


    # full_tokenizer.max_len = dim

    # if args.device==''
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    #强制使用cpu
    device = args.device

    print('using device:', device)

    raw_data_path = args.raw_data_path
    tokenized_data_path = args.tokenized_data_path
    raw = args.raw  # 选择是否从零开始构建数据集
    pretrained_model = args.pretrained_model
    epochs = args.epochs
    batch_size = args.batch_size
    lr = args.lr
    warmup_steps = args.warmup_steps
    log_step = args.log_step
    stride = args.stride
    dim=args.dim
    if stride>= dim:
        stride=dim/2-2
    gradient_accumulation = args.gradient_accumulation
    
    # fp16 = args.fp16  # 不支持半精度的显卡请勿打开
    # fp16_opt_level = args.fp16_opt_level
    max_grad_norm = args.max_grad_norm
    num_pieces = args.num_pieces
    min_length = args.min_length
    output_dir = args.output_dir
    # tb_writer = SummaryWriter(log_dir=args.writer_dir)

    # 加载之前的模型路径
    model_path=os.path.join(pretrained_model, 'model.pt')
    optimizer_path= os.path.join(pretrained_model, 'optimizer.pt')
    scheduler_path=os.path.join(pretrained_model, 'scheduler.pt')
    # 设置输出
    output_model_path=os.path.join(output_dir, 'model.pt')
    output_optimizer_path= os.path.join(output_dir, 'optimizer.pt')
    output_scheduler_path=os.path.join(output_dir, 'scheduler.pt')

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)


    weight_decay=0.0
    adam_epsilon=1e-8
    max_grad_norm=1.0
    max_steps=-1

    logging_steps=1000
    save_steps=10000

    DE_SEQ_LEN = 256
    EN_SEQ_LEN = 256
    model = ReformerEncDec(
        dim = args.dim,
        enc_num_tokens = full_tokenizer.vocab_size,
        enc_depth = args.enc_depth,
        enc_max_seq_len =EN_SEQ_LEN ,
        dec_num_tokens = full_tokenizer.vocab_size,
        dec_depth = args.dec_depth,
        dec_max_seq_len = DE_SEQ_LEN
    )



    # 加载模型
    if os.path.isfile(model_path):
        # if so, load them
        model.load_state_dict(torch.load(model_path))
    else:   
        # pass
        model.train()

    #模型载入到cuda
    if device=='cuda':
        model.to('cuda')
    else:
        pass



    no_decay = ['bias', 'LayerNorm.weight']
    optimizer_grouped_parameters = [
        {
            'params': [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
            'weight_decay': weight_decay
        },
        {
            'params': [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
            'weight_decay': 0.0
        }
    ]

    # 加载数据
    datas=[]
    if args.raw:

        for item in tqdm(build_files(data_path=raw_data_path, tokenized_data_path=tokenized_data_path, num_pieces=num_pieces,full_tokenizer=full_tokenizer, max_length_input=EN_SEQ_LEN,max_length_output=DE_SEQ_LEN)):
            datas.append(item)
        f=open(tokenized_data_path+"data.pk","wb")
        pickle.dump(datas,f)
        #只进行数据预处理
        if args.raw_only:
            exit()
    else:
        f=open(tokenized_data_path+"data.pk","rb")
        datas=pickle.load(f)
    if args.max_data>0:
        data=datas[:args.max_data]
    log_json=tkitJson.Json(output_dir+"log.json")

    # 总步数
    total_steps =math.ceil( len(datas)*(epochs+1)/batch_size /gradient_accumulation)
    #优化器
    optimizer = AdamW(optimizer_grouped_parameters, lr=lr, eps=adam_epsilon)
    scheduler = get_linear_schedule_with_warmup( optimizer=optimizer, num_warmup_steps=warmup_steps,num_training_steps=total_steps)

    # # checking if another optimizer/scheduler exists
    if os.path.isfile(optimizer_path) and os.path.isfile(scheduler_path):
        # if so, load them
        optimizer.load_state_dict(torch.load(optimizer_path))
        scheduler.load_state_dict(torch.load(scheduler_path))

    print("optimizer",optimizer)


    #小数据训练
    # datas=datas[:1500]  
    print('starting training')
    overall_step = 0
    gradient_accumulation_run=0
    Db=DB(password=args.password)
    Db.clear_col()
    all_time=[]
    for epoch in range(epochs):
        print('epoch {}'.format(epoch + 1))
        now = datetime.now()
        # print('time: {}'.format(now))
        # 进行随机打乱
        random.shuffle(datas)
        samples=datas
        for step in range(len(samples) // batch_size):  # drop last

            batch = samples[step * batch_size: (step + 1) * batch_size]

            train_seq_in=[]
            train_seq_out=[]
            input_mask=[]
            for batchA,batchB in batch:
                # print(len(batchA))
                # print(len(batchB))
                train_seq_in.append(batchA)
                train_seq_out.append(batchB)
                input_mask.append([1]*len(batchA))



            if device=='cuda':
                train_seq_in = torch.tensor(train_seq_in).long().to("cuda")
                train_seq_out = torch.tensor(train_seq_out).long().to("cuda")
                input_mask= torch.tensor(input_mask).bool().to("cuda")
            else:
                train_seq_in = torch.tensor(train_seq_in).long()
                train_seq_out = torch.tensor(train_seq_out).long()
                input_mask= torch.tensor(input_mask).bool()
            # input_mask = torch.ones(1, EN_SEQ_LEN,batch_size).bool()
            # print(input_mask)
            # print(train_seq_in.size())
            # print(train_seq_out.size())
            # print(input_mask.size())
            loss = model(train_seq_in, train_seq_out, return_loss = True, enc_input_mask = input_mask)
            # loss = model(batch_inputs, return_loss = True)
            # print("loss",loss.item())
            # exit()
            loss = loss/gradient_accumulation   
            loss.backward()
            # print(loss.sum())
            if((gradient_accumulation_run+1)%gradient_accumulation)==0:
                # optimizer the net
                optimizer.step()
                scheduler.step()        # update parameters of net
                optimizer.zero_grad()        # update parameters of net
                end = datetime.now()
                overall_step+=1
                # print("epoch:",epoch + 1," piece_num:",piece_num,'/',num_pieces," step:",overall_step+1,'/',total_steps," step完成比例:",(overall_step+1)/total_steps," loss:",loss.item(),'Time',end-now)
                # all_time.append(end-now)
                pre_time=(end-now)*(total_steps-overall_step)
                
                print("epoch:",epoch + 1," step:",overall_step,'/',total_steps," step完成比例:",(overall_step)/total_steps," loss:",loss.item(),"剩余时间:",pre_time)


                log_one={
                    "epoch":epoch+1,
                    "loss":loss.item(),
                    "step":overall_step
                }
                if args.db_loss:
                    # print("log_one",log_one)
                    Db.add_one(log_one)
                log_json.save([log_one])
                now = datetime.now()   
            gradient_accumulation_run=gradient_accumulation_run+1
            
            torch.save(model.state_dict(),  output_model_path)
            torch.save(optimizer.state_dict(), output_optimizer_path)
            torch.save(scheduler.state_dict(),  output_scheduler_path)
    # model_cpu_path=os.path.join(output_dir, 'model_cpu.pt')
    torch.save(model.cpu().state_dict(), model_cpu_path)
if __name__ == '__main__':
    main()


def get(start_text):
  """
  获取预测文本
  """
  # start_text=x_train_text[0][:5]
  initial =auto(start_text)
  initial
  sample = model.generate(initial, 30, temperature=1., filter_thres = 0.9, eos_token = 1) # assume end token is 1, or omit and it will sample up to 100
  # print(sample)
  # print(sample.shape) # (1, <=100) token ids
  text = tokenizer.convert_ids_to_tokens(sample.tolist()[0])
  return text
