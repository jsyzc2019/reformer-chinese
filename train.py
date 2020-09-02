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
import pre_process_data as ppd
import pickle
from transformers import *
import torch
import os
from torch import randint
import torch.nn as nn
from reformer_pytorch import ReformerLM
from reformer_pytorch.generative_tools import TrainingWrapper
from reformer_chinese import *
import tkitJson
import shutil
def build_files(data_path, tokenized_data_path, num_pieces, full_tokenizer, min_length):
    if ppd.is_default_file_type():  # 是否采用默认json类型，默认编码为utf-8
        if ppd.DEFAULT_FILE_TYPE in data_path:
            with open(data_path, 'r', encoding='utf8') as f:
                print('reading lines')
                lines = json.load(f)
                new_lines=[]

                lines = [line.replace('\n', ' [SEP] ') for line in lines]  # 用[SEP]表示换行, 段落之间使用SEP表示段落结束
                for line in lines:
                    if line in[' [SEP] ']:
                        # print("eee")
                        pass
                    else:
                        new_lines.append(line)
                lines=new_lines
                

        else:
            raise Exception("请使用json文件类型，或者自定义文件类型，请看pre_process_data.py文件load方法")
    else:  # 自定义数据源的，调用pre_process_data.py中的load方法
        lines = ppd.load()
    all_len = len(lines)
    if not os.path.exists(tokenized_data_path):
        os.mkdir(tokenized_data_path)
    for i in tqdm(range(num_pieces)):
        sublines = lines[all_len // num_pieces * i: all_len // num_pieces * (i + 1)]
        # print(sublines)
        if i == num_pieces - 1:
            sublines.extend(lines[all_len // num_pieces * (i + 1):])  # 把尾部例子添加到最后一个piece
        sublines = [full_tokenizer.tokenize(line) for line in tqdm(sublines) if
                    len(line) > min_length]  # 只考虑长度超过min_length的句子
        # print(sublines)
        sublines = [full_tokenizer.convert_tokens_to_ids(line) for line in tqdm(sublines)]
        full_line = []
        for subline in sublines:

            full_line.append(full_tokenizer.convert_tokens_to_ids('[MASK]'))  # 文章开头添加MASK表示文章开始
            full_line.extend(subline)
            full_line.append(full_tokenizer.convert_tokens_to_ids('[CLS]'))  # 文章之间添加CLS表示文章结束
        with open(tokenized_data_path + 'tokenized_train_{}.txt'.format(i), 'w') as f:
            for id in full_line:
                f.write(str(id) + ' ')
    print('finish')

# sentence_0 = "你是谁啊"
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
    parser.add_argument('--tokenized_data_path', default='data/tokenized/', type=str, required=False,
                        help='tokenized语料存放位置')
    parser.add_argument('--raw', action='store_true', help='是否先做tokenize')
    parser.add_argument('--epochs', default=5, type=int, required=False, help='训练循环')
    parser.add_argument('--batch_size', default=2, type=int, required=False, help='训练batch size')
    parser.add_argument('--lr', default=1e-8, type=float, required=False, help='学习率')
    parser.add_argument('--warmup_steps', default=2000, type=int, required=False, help='warm up步数')
    parser.add_argument('--log_step', default=1, type=int, required=False, help='多少步汇报一次loss')
    parser.add_argument('--stride', default=500, type=int, required=False, help=' 向前跨越的长度')
    parser.add_argument('--dim', default=1024, type=int, required=False, help='训练时取训练数据的窗口步长单个样本长度')
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

    # parser.add_argument('--dim', default=1024, type=int, required=False, help='dim')
    parser.add_argument('--depth', default=12, type=int, required=False, help='depth')
    parser.add_argument('--full_attn_thres', default=1024, type=int, required=False, help='full_attn_thres')
    parser.add_argument('--max_seq_len', default=4096, type=int, required=False, help='max_seq_len')
    # parser.add_argument('--encoder_json', default="tokenizations/encoder.json", type=str, help="encoder.json")
    # parser.add_argument('--vocab_bpe', default="tokenizations/vocab.bpe", type=str, help="vocab.bpe")

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

    # model_config = transformers.modeling_gpt2.GPT2Config.from_json_file(args.model_config)
    # print('config:\n' + model_config.to_json_string())

    # dim = model_config.dim
    # if args.bpe_token:
    #     full_tokenizer = get_encoder(args.encoder_json, args.vocab_bpe)
    # else:
    # full_tokenizer = tokenization_bert.BertTokenizer(vocab_file=args.tokenizer_path)
    # full_tokenizer = BertTokenizer.from_pretrained(args.tokenizer_path)

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

    if raw:
        print('building files')
        build_files(data_path=raw_data_path, tokenized_data_path=tokenized_data_path, num_pieces=num_pieces,
                    full_tokenizer=full_tokenizer, min_length=min_length)
        print('files built')

    model = ReformerLM(
        num_tokens= full_tokenizer.vocab_size,
        dim = dim, #窗口长度
        depth = args.depth,
        max_seq_len =  args.max_seq_len,
        lsh_dropout = 0.1,
        causal = True,
        full_attn_thres = args.full_attn_thres
    )

    # 0 is used for padding and no loss to be calculated on it
    if device=='cuda':
        model = TrainingWrapper(model, ignore_index = 0, pad_value = 0).to('cuda')
    else:
        model = TrainingWrapper(model, ignore_index = 0, pad_value = 0)

    if os.path.isfile(model_path):
        # if so, load them
        model.load_state_dict(torch.load(model_path))
    else:   
        # pass
        model.train()

    weight_decay=0.0
    # learning_rate=5e-5
    adam_epsilon=1e-8
    # warmup_steps=0
    max_grad_norm=1.0
    max_steps=-1
    # gradient_accumulation_steps=10
    logging_steps=1000
    save_steps=10000
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


    full_len = 0
    print('calculating total steps')
    for i in tqdm(range(num_pieces)):
        with open(tokenized_data_path + 'tokenized_train_{}.txt'.format(i), 'r') as f:
            full_len += len([int(item) for item in f.read().strip().split()])
    total_steps = int(full_len / stride * epochs / batch_size / gradient_accumulation)
    print('total steps = {}'.format(total_steps))



    # total_steps = len(x_train_text)/gradient_accumulation_steps * num_train_epochs
    # t_total=3/1*3
    # optimizer = AdamW(model.parameters(), lr=lr, correct_bias=True)
    optimizer = AdamW(optimizer_grouped_parameters, lr=lr, eps=adam_epsilon)
    scheduler = get_linear_schedule_with_warmup( optimizer=optimizer, num_warmup_steps=warmup_steps,num_training_steps=total_steps)

    # # checking if another optimizer/scheduler exists
    if os.path.isfile(optimizer_path) and os.path.isfile(scheduler_path):
        # if so, load them
        optimizer.load_state_dict(torch.load(optimizer_path))
        scheduler.load_state_dict(torch.load(scheduler_path))

    print("optimizer",optimizer)
    loss_fn=nn.CrossEntropyLoss()

    
    print('starting training')
    overall_step = 0
    running_loss = 0
    gradient_accumulation_run=0
    for epoch in range(epochs):
        print('epoch {}'.format(epoch + 1))
        now = datetime.now()
        print('time: {}'.format(now))
        x = np.linspace(0, num_pieces - 1, num_pieces, dtype=np.int32)
        random.shuffle(x)
        # piece_num = 0

        # model.zero_grad()   # reset gradient
        # for piece_num, i in tqdm(enumerate( x)):
        for piece_num, i in enumerate( x):
            with open(tokenized_data_path + 'tokenized_train_{}.txt'.format(i), 'r') as f:
                line = f.read().strip()
            tokens = line.split()
            tokens = [int(token) for token in tokens]
            #  print(len(tokens))
            start_point = 0
            samples = []
            #划窗切割数据
            while start_point < len(tokens) - dim:
                samples.append(tokens[start_point: start_point + dim])
                #  print(start_point, start_point + dim)
                start_point += stride
            if start_point < len(tokens):
                samples.append(tokens[len(tokens)-dim:])
            # 打乱数据，防止过度拟合
#              for it in samples[:10]:
                #  print(len(it))
#
            random.shuffle(samples)
            for step in range(len(samples) // batch_size):  # drop last
                # print(step)
                #  prepare data
                batch = samples[step * batch_size: (step + 1) * batch_size]
                # batch_labels = []
                batch_inputs = []
                for ids in batch:
                    # int_ids_for_labels = [int(x) for x in ids]
                    int_ids_for_inputs = [int(x) for x in ids]
                    # batch_labels.append(int_ids_for_labels)
                    batch_inputs.append(int_ids_for_inputs)
                if device=='cuda':
                    batch_inputs = torch.tensor(batch_inputs).long().to("cuda")
                    # batch_labels = torch.tensor(batch_labels).long().to("cuda")
                else:
                    batch_inputs = torch.tensor(batch_inputs).long()
                    # batch_labels = torch.tensor(batch_labels).long()
                # batch_inputs = torch.tensor(batch_inputs).long().to(device)
                # print(batch_labels)

                # print(len(batch_inputs))
                # print(batch_inputs)
                # print(len(batch_inputs))

                loss = model(batch_inputs, return_loss = True)
                loss = loss/gradient_accumulation   
                loss.backward()
                # print(loss.sum())
                if((gradient_accumulation_run+1)%gradient_accumulation)==0:
                    # optimizer the net
                    optimizer.step()
                    scheduler.step()        # update parameters of net
                    optimizer.zero_grad()        # update parameters of net
                    # scheduler.zero_grad()        # update parameters of net
                    # model.zero_grad()   # reset gradient
                    end = datetime.now()
                    print("epoch:",epoch + 1," piece_num:",piece_num,'/',num_pieces," step:",overall_step+1,'/',total_steps," step完成比例:",(overall_step+1)/total_steps," loss:",loss.item(),'Time',end-now)
                overall_step+=1
                gradient_accumulation_run=gradient_accumulation_run+1

                # scheduler.step()
                # model.zero_grad()
            # end = datetime.now()
            # print("one piece:",end-now," s")

            torch.save(model.state_dict(),  output_model_path)
            torch.save(optimizer.state_dict(), output_optimizer_path)
            torch.save(scheduler.state_dict(),  output_scheduler_path)
    model_cpu_path=os.path.join(output_dir, 'model_cpu.pt')
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
