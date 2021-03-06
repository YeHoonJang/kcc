import tqdm
import pickle

import torch
from torch.utils.data import DataLoader

import sentencepiece as spm

from custom_dataset import CustomDataset
from models.rnn.model import Encoder, TSTDecoder, NMTDecoder, StyleTransfer, StylizedNMT
from loss import ce_loss, kl_loss

# os.environ['CUDA_LAUNCH_BLOCKING'] = "1"

torch.cuda.empty_cache()
torch.autograd.set_detect_anomaly(True)

def tst_train_one_epoch(args, tst_model, epoch, data_loader, tst_optimizer, device):
    tst_model.train()

    train_loss = 0.0
    total = len(data_loader)

    with tqdm.tqdm(total=total) as pbar:
        for _, (src, trg) in enumerate(data_loader):
            src = src.to(device)
            trg = trg.to(device)

            tst_out, latent_variables, output_list = tst_model(src, trg)

            tst_out = tst_out[:, 1:].reshape(-1, tst_out.size(-1))

            trg_trg = trg[:, 1:].reshape(-1)

            CE_loss = ce_loss(tst_out, trg_trg)
            total_latent = latent_variables[0]
            style_mu, style_logv = latent_variables[-2:]
            if style_mu is None:
                tst_loss = CE_loss
            else:
                KL_loss, KL_weight = kl_loss(style_mu, style_logv, epoch, 0.0025, 2500)
                tst_loss = (CE_loss + KL_loss * KL_weight)

            loss_value = tst_loss.item()
            train_loss = train_loss + loss_value

            tst_optimizer.zero_grad()  # optimizer 초기화
            # tst_loss.backward(retain_graph=True)
            tst_loss.backward(retain_graph=True)
            tst_optimizer.step()  # Gradient Descent 시작
            pbar.update(1)

    return train_loss / total, total_latent, trg[:, 1:].tolist(), output_list


@torch.no_grad()    #no autograd (backpropagation X)
def tst_evaluate(args, tst_model, epoch, data_loader, device):
    tst_model.eval()

    valid_loss = 0.0
    total = len(data_loader)

    with tqdm.tqdm(total=total) as pbar:
        for _, (src, trg) in enumerate(data_loader):
            src = src.to(device)
            trg = trg.to(device)

            tst_out, latent_variables, output_list = tst_model(src, trg)

            tst_out = tst_out[:, 1:].reshape(-1, tst_out.size(-1))

            trg_trg = trg[:, 1:].reshape(-1)

            CE_loss = ce_loss(tst_out, trg_trg)
            style_mu, style_logv = latent_variables[-2:]
            if style_mu is None:
                tst_loss = CE_loss
            else:
                KL_loss, KL_weight = kl_loss(style_mu, style_logv, epoch, 0.0025, 2500)
                tst_loss = (CE_loss + KL_loss * KL_weight)
            loss_value = tst_loss.item()
            valid_loss = valid_loss + loss_value

            pbar.update(1)

    return valid_loss / total, trg[:, 1:].tolist(), output_list

def nmt_train_one_epoch(args, nmt_model, data_loader, nmt_optimizer, device):
    nmt_model.train()

    train_loss = 0.0
    total = len(data_loader)

    with tqdm.tqdm(total=total) as pbar:
        for _, (src, trg) in enumerate(data_loader):
            src = src.to(device)
            trg = trg.to(device)
            #
            # _, nmt_hidden, nmt_cell = tst_encoder(src)
            #
            # nmt_hidden = nmt_hidden.detach().to(device)
            # nmt_cell = nmt_cell.detach().to(device)
            # # nmt_hidden = nmt_hidden.to(device)
            # # nmt_cell = nmt_cell.to(device)

            nmt_out, output_list = nmt_model(src, trg)

            nmt_out = nmt_out[:, 1:].reshape(-1, nmt_out.size(-1))

            trg_trg = trg[:, 1:].reshape(-1)


            nmt_loss = ce_loss(nmt_out, trg_trg)
            loss_value = nmt_loss.item()
            train_loss = train_loss + loss_value

            nmt_optimizer.zero_grad()  # optimizer 초기화
            # nmt_loss.requires_grad_(True)
            nmt_loss.backward()
            nmt_optimizer.step()    # Gradient Descent 시작

            pbar.update(1)

    return train_loss/total, trg[:, 1:].tolist(), output_list

@torch.no_grad()    #no autograd (backpropagation X)
def nmt_evaluate(args, nmt_model, data_loader, device):
    nmt_model.eval()

    valid_loss = 0.0
    total = len(data_loader)

    with tqdm.tqdm(total=total) as pbar:
        for _, (src, trg) in enumerate(data_loader):
            src = src.to(device)
            trg = trg.to(device)

            #
            # _, nmt_hidden, nmt_cell = tst_encoder(src)
            #
            # nmt_hidden = nmt_hidden.detach().to(device)
            # nmt_cell = nmt_cell.detach().to(device)
            # # nmt_hidden = nmt_hidden.to(device)
            # # nmt_cell = nmt_cell.to(device)

            nmt_out, output_list = nmt_model(src, trg)

            nmt_out = nmt_out[:, 1:].reshape(-1, nmt_out.size(-1))

            trg_trg = trg[:, 1:].reshape(-1)

            CE_loss = ce_loss(nmt_out, trg_trg)
            nmt_loss = CE_loss
            loss_value = nmt_loss.item()
            valid_loss = valid_loss + loss_value

            pbar.update(1)

    return valid_loss/total, trg[:, 1:].tolist(), output_list

def train(args):
    # Device Setting
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Initializing Device: {device}')
    print(f'Count of using GPUs:{torch.cuda.device_count()}')

    # Data Setting
    with open("/HDD/yehoon/data/processed/tokenized/spm_tokenized_data.pkl", "rb") as f:
        data = pickle.load(f)
        f.close()

    em_informal_train = data["gyafc"]["train"]["em_informal"]
    em_formal_train = data["gyafc"]["train"]["em_formal"]
    pair_kor_train = data['korpora']['train']['pair_kor']
    pair_eng_train = data['korpora']['train']['pair_eng']
    # fr_informal_train = data["gyafc"]["train"]["fr_informal"]
    # fr_formal_train = data["gyafc"]["train"]["fr_formal"]

    split_ratio = 0.8
    em_informal_train = em_informal_train[:int(len(em_informal_train) * split_ratio)]
    em_informal_valid = em_informal_train[int(len(em_informal_train) * split_ratio):]
    em_formal_train = em_formal_train[:int(len(em_formal_train) * split_ratio)]
    em_formal_valid = em_formal_train[int(len(em_formal_train) * split_ratio):]
    pair_kor_train = pair_kor_train[:int(len(pair_kor_train) * split_ratio)]
    pair_kor_valid = pair_kor_train[int(len(pair_kor_train) * split_ratio):]
    pair_eng_train = pair_eng_train[:int(len(pair_eng_train) * split_ratio)]
    pair_eng_valid = pair_eng_train[int(len(pair_eng_train) * split_ratio):]

    #
    # em_informal_test = data["gyafc"]["test"]["em_informal"]
    # em_formal_test = data["gyafc"]["test"]["em_formal"]
    # pair_kor_test = data['korpora']['test']['pair_kor']
    # pair_eng_test = data['korpora']['test']['pair_eng']
    # fr_informal_test = data["gyafc"]["test"]["fr_informal"]
    # fr_formal_test = data["gyafc"]["test"]["fr_formal"]


    # TODO argparse
    min_len, max_len = 2, 300
    batch_size = 100
    num_workers = 0
    tst_vocab_size = 1800
    nmt_vocab_size = 2400

    tst_train_data = CustomDataset(em_informal_train, em_formal_train, min_len, max_len)
    tst_valid_data = CustomDataset(em_informal_valid, em_formal_valid, min_len, max_len)
    # tst_test_data = CustomDataset(em_informal_test, em_formal_test, min_len, max_len)

    nmt_train_data = CustomDataset(pair_eng_train, pair_kor_train, min_len, max_len)
    nmt_valid_data = CustomDataset(pair_eng_valid, pair_kor_valid, min_len, max_len)
    # nmt_test_data = CustomDataset(pair_eng_test, pair_kor_test, min_len, max_len)

    tst_train_loader = DataLoader(tst_train_data, batch_size=batch_size, drop_last=True, shuffle=True,
                                  num_workers=num_workers)
    tst_valid_loader = DataLoader(tst_valid_data, batch_size=batch_size, drop_last=True, shuffle=True,
                                  num_workers=num_workers)
    # tst_test_loader = DataLoader(tst_test_data, batch_size=batch_size, drop_last=True, shuffle=True,
    #                              num_workers=num_workers)

    nmt_train_loader = DataLoader(nmt_train_data, batch_size=batch_size, drop_last=True, shuffle=True,
                                  num_workers=num_workers)
    nmt_valid_loader = DataLoader(nmt_valid_data, batch_size=batch_size, drop_last=True, shuffle=True,
                                  num_workers=num_workers)
    # nmt_test_loader = DataLoader(nmt_test_data, batch_size=batch_size, drop_last=True, shuffle=True,
    #                              num_workers=num_workers)


    # TST Train
    tst_encoder = Encoder(input_size=nmt_vocab_size, d_hidden=1024, d_embed=256, n_layers=2, dropout=0.1, device=device)
    tst_decoder = TSTDecoder(output_size=tst_vocab_size, d_hidden=1024, d_embed=256, n_layers=2, dropout=0.1, device=device)
    tst_model = StyleTransfer(tst_encoder, tst_decoder, d_hidden=1024, style_ratio=0.3, variational=args.variational, device=device)
    tst_model = tst_model.to(device)

    tst_optimizer = torch.optim.AdamW(tst_model.parameters(), lr=0.001)

    start_epoch = 0
    epochs = 20

    print("Start TST Training..")

    tst_tokenizer = spm.SentencePieceProcessor()
    tst_tokenizer.Load("/HDD/yehoon/data/tokenizer/train_em_formal_spm.model")

    tst_train_decode_output = []
    tst_valid_decode_output = []

    for epoch in range(start_epoch, epochs+1):
        print(f"Epoch: {epoch}")

        epoch_loss, total_latent, tst_train_trg_list, tst_train_out_list = tst_train_one_epoch(args, tst_model, epoch, tst_train_loader, tst_optimizer, device)
        print(f"Training Loss: {epoch_loss:.2f}")

        valid_loss, tst_valid_trg_list, tst_valid_out_list = tst_evaluate(args, tst_model, epoch, tst_valid_loader, device)
        print(f"Validation Loss: {valid_loss:.2f}")

        tst_train_out_list = list(map(list, zip(*tst_train_out_list)))
        tst_valid_out_list = list(map(list, zip(*tst_valid_out_list)))

        tst_train_target_decode = [tst_tokenizer.DecodeIds(i) for i in tst_train_trg_list]
        tst_train_output_decoder = [tst_tokenizer.DecodeIds(j) for j in tst_train_out_list]
        tst_train_decode_output.append((tst_train_target_decode, tst_train_output_decoder))

        tst_valid_target_decode = [tst_tokenizer.DecodeIds(i) for i in tst_valid_trg_list]
        tst_valid_output_decoder = [tst_tokenizer.DecodeIds(j) for j in tst_valid_out_list]
        tst_valid_decode_output.append((tst_valid_target_decode, tst_valid_output_decoder))

    # model save
    torch.save({'model': tst_model.state_dict(),
                'encoder': tst_model.encoder.state_dict(),
                'total_latent': total_latent}, "/HDD/yehoon/data/v_tst_model.pth")

    with open("/HDD/yehoon/data/n_tst_train_target_decode.txt", "w", encoding="utf8") as tf, open(
            "/HDD/yehoon/data/v_tst_train_output_decode.txt", "w", encoding="utf8") as of:
        for t_line, o_line in tst_train_decode_output:
            for tline in t_line:
                tf.write(f"{tline}\n")
            for oline in o_line:
                of.write(f"{oline}\n")
        tf.close()
        of.close()

    with open ("/HDD/yehoon/data/v_tst_valid_target_decode.txt", "w", encoding="utf8") as tf, open("/HDD/yehoon/data/v_tst_valid_output_decode.txt", "w", encoding="utf8") as of:
        for t_line, o_line in tst_valid_decode_output:
            for tline in t_line:
                tf.write(f"{tline}\n")
            for oline in o_line:
                of.write(f"{oline}\n")
        tf.close()
        of.close()


    # NMT Train

    # nmt_encoder = tst_model.encoder.requires_grad_(False)
    # nmt_encoder = tst_model.encoder
    # nmt_encoder = nmt_encoder.to(device)
    nmt_encoder = Encoder(input_size=nmt_vocab_size, d_hidden=1024, d_embed=256, n_layers=2, dropout=0.1, device=device)
    nmt_decoder = NMTDecoder(output_size=nmt_vocab_size, d_hidden=1024, d_embed=256, n_layers=2, dropout=0.1, device=device)
    nmt_model = StylizedNMT(nmt_encoder, nmt_decoder, d_hidden=1024, total_latent=total_latent, device=device)
    nmt_model = nmt_model.to(device)

    nmt_optimizer = torch.optim.AdamW(nmt_model.nmt_decoder.parameters(), lr=0.001)

    start_epoch = 0
    epochs = 20

    print("Start NMT Training..")

    nmt_tokenizer = spm.SentencePieceProcessor()
    nmt_tokenizer.Load("/HDD/yehoon/data/tokenizer/train_pair_kor_spm.model")

    nmt_train_decode_output = []
    nmt_valid_decode_output = []

    for epoch in range(start_epoch, epochs + 1):
        print(f"Epoch: {epoch}")
        epoch_loss , nmt_train_trg_list, nmt_train_out_list= nmt_train_one_epoch(args, nmt_model, nmt_train_loader, nmt_optimizer, device)
        print(f"Training Loss: {epoch_loss:.2f}")

        valid_loss, nmt_valid_trg_list, nmt_valid_out_list = nmt_evaluate(args, nmt_model, nmt_valid_loader, device)
        print(f"Validation Loss: {valid_loss:.2f}")

        nmt_train_out_list = list(map(list, zip(*nmt_train_out_list)))
        nmt_valid_out_list = list(map(list, zip(*nmt_valid_out_list)))

        nmt_train_target_decode = [nmt_tokenizer.DecodeIds(i) for i in nmt_train_trg_list]
        nmt_train_output_decoder = [nmt_tokenizer.DecodeIds(j) for j in nmt_train_out_list]
        nmt_train_decode_output.append((nmt_train_target_decode, nmt_train_output_decoder))

        nmt_valid_target_decode = [nmt_tokenizer.DecodeIds(i) for i in nmt_valid_trg_list]
        nmt_valid_output_decoder = [nmt_tokenizer.DecodeIds(j) for j in nmt_valid_out_list]
        nmt_valid_decode_output.append((nmt_valid_target_decode, nmt_valid_output_decoder))

    # model save
    torch.save({'model': nmt_model.state_dict(),
                'encoder': nmt_model.encoder.state_dict()}, "/HDD/yehoon/data/v_ed_nmt_model.pth")

    with open("/HDD/yehoon/data/v_ed_nmt_train_target_decode.txt", "w", encoding="utf8") as tf, open("/HDD/yehoon/data/v_ed_nmt_train_output_decode.txt", "w", encoding="utf8") as of:
        for t_line, o_line in nmt_train_decode_output:
            for tline in t_line:
                tf.write(f"{tline}\n")
            for oline in o_line:
                of.write(f"{oline}\n")
        tf.close()
        of.close()

    with open("/HDD/yehoon/data/v_ed_nmt_valid_target_decode.txt", "w", encoding="utf8") as tf, open(
            "/HDD/yehoon/data/v_ed_nmt_valid_output_decode.txt", "w", encoding="utf8") as of:
        for t_line, o_line in nmt_valid_decode_output:
            for tline in t_line:
                tf.write(f"{tline}\n")
            for oline in o_line:
                of.write(f"{oline}\n")
        tf.close()
        of.close()