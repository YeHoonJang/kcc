''' Translate input text with trained model. '''
import os
import argparse
import dill as pickle
from tqdm import tqdm

import torch
from torch import nn
import sentencepiece as spm

import transformer.Constants as Constants
from torchtext.data import Dataset
from transformer.TM_Models import Transformer, VAETransformer, NMTEncoder
from transformer.Translator import Translator


def load_model(opt, device):
    checkpoint = torch.load(opt.model, map_location=device)
    model_opt = checkpoint['settings']
    if opt.variational:
        nmt_encoder = NMTEncoder(
            n_src_vocab=model_opt.src_vocab_size, n_position=200,
            d_word_vec=model_opt.d_word_vec, d_model=model_opt.d_model,
            d_inner=model_opt.d_inner_hid,
            n_layers=model_opt.n_layers, n_head=model_opt.n_head,
            d_k=model_opt.d_k, d_v=model_opt.d_v,
            pad_idx=model_opt.src_pad_idx, dropout=model_opt.dropout,
            scale_emb=False).to(device)
        nmt_encoder.load_state_dict(checkpoint['encoder'])



        model = VAETransformer(
            nmt_encoder,
            model_opt.src_vocab_size,
            model_opt.trg_vocab_size,

            model_opt.src_pad_idx,
            model_opt.trg_pad_idx,

            trg_emb_prj_weight_sharing=model_opt.proj_share_weight,
            emb_src_trg_weight_sharing=model_opt.embs_share_weight,
            d_k=model_opt.d_k,
            d_v=model_opt.d_v,
            d_model=model_opt.d_model,
            d_latent=model_opt.d_latent,
            d_word_vec=model_opt.d_word_vec,
            d_inner=model_opt.d_inner_hid,
            n_layers=model_opt.n_layers,
            n_head=model_opt.n_head,
            dropout=model_opt.dropout).to(device)
        model.load_state_dict(checkpoint['model'])
        print('[Info] Trained model state loaded.')
        return model
    # elif opt.split:
    #     model = DualVAETransformer(
    #         opt.task_type,
    #         model_opt.src_vocab_size,
    #         model_opt.trg_vocab_size,
    #
    #         model_opt.src_pad_idx,
    #         model_opt.trg_pad_idx,
    #
    #         trg_emb_prj_weight_sharing=model_opt.proj_share_weight,
    #         emb_src_trg_weight_sharing=model_opt.embs_share_weight,
    #         d_k=model_opt.d_k,
    #         d_v=model_opt.d_v,
    #         d_model=model_opt.d_model,
    #         d_latent=model_opt.d_latent,
    #         d_word_vec=model_opt.d_word_vec,
    #         d_inner=model_opt.d_inner_hid,
    #         n_layers=model_opt.n_layers,
    #         n_head=model_opt.n_head,
    #         dropout=model_opt.dropout).to(device)
    #     model.load_state_dict(checkpoint['model'])
        print('[Info] Trained model state loaded.')
        return model
    else:
        model = Transformer(
            model_opt.src_vocab_size,
            model_opt.trg_vocab_size,

            model_opt.src_pad_idx,
            model_opt.trg_pad_idx,

            trg_emb_prj_weight_sharing=model_opt.proj_share_weight,
            emb_src_trg_weight_sharing=model_opt.embs_share_weight,
            d_k=model_opt.d_k,
            d_v=model_opt.d_v,
            d_model=model_opt.d_model,
            d_word_vec=model_opt.d_word_vec,
            d_inner=model_opt.d_inner_hid,
            n_layers=model_opt.n_layers,
            n_head=model_opt.n_head,
            dropout=model_opt.dropout).to(device)
        model.load_state_dict(checkpoint['model'])
        print('[Info] Trained model state loaded.')
        return model




def main():
    '''Main Function'''

    parser = argparse.ArgumentParser(description='translate.py')

    parser.add_argument('-model', required=True,
                        help='Path to model weight file')
    parser.add_argument('-data_pkl', required=True,
                        help='Pickle file with both instances and vocabulary.')
    parser.add_argument('-output', default='output/pred_text',
                        help="""Path to output the predictions (each line will
                        be the decoded sequence""")
    parser.add_argument('-file_name', default=None)
    parser.add_argument('-beam_size', type=int, default=5)
    parser.add_argument('-max_seq_len', type=int, default=100)
    parser.add_argument('-no_cuda', action='store_true')
    parser.add_argument('-variational', action='store_true')
    parser.add_argument('-split', action='store_true')
    parser.add_argument('-task_type', type=str, default=None, choices=["tst", "nmt"])

    # TODO: Translate bpe encoded files 
    #parser.add_argument('-src', required=True,
    #                    help='Source sequence to decode (one line per sequence)')
    #parser.add_argument('-vocab', required=True,
    #                    help='Source sequence to decode (one line per sequence)')
    # TODO: Batch translation
    parser.add_argument('-batch_size', type=int, default=30,
                       help='Batch size')
    #parser.add_argument('-n_best', type=int, default=1,
    #                    help="""If verbose is set, will output the n_best
    #                    decoded sentences""")

    opt = parser.parse_args()
    opt.cuda = not opt.no_cuda

    data = pickle.load(open(opt.data_pkl, 'rb'))
    tst_data = pickle.load(open(".data/pkl/gyafc_spm_bpe.pkl", "rb"))
    SRC = tst_data['vocab']['src']
    TRG = data['vocab']['trg']
    # print("SRC", )
    opt.src_pad_idx = SRC.vocab.stoi[Constants.PAD_WORD]
    opt.trg_pad_idx = TRG.vocab.stoi[Constants.PAD_WORD]
    opt.trg_bos_idx = TRG.vocab.stoi[Constants.BOS_WORD]
    opt.trg_eos_idx = TRG.vocab.stoi[Constants.EOS_WORD]
    # print("opt.src_pad_idx", opt.src_pad_idx) 1
    # print("opt.trg_pad_idx", opt.trg_pad_idx) 1
    # print("opt.trg_bos_idx", opt.trg_bos_idx) 2
    # print("opt.trg_eos_idx", opt.trg_eos_idx) 3

    test_loader = Dataset(examples=data['test'], fields={'src': SRC, 'trg': TRG})
    
    device = torch.device('cuda' if opt.cuda else 'cpu')
    checkpoint = torch.load(opt.model, map_location=device)
    model_opt = checkpoint['settings']
    translator = Translator(opt,
        model=load_model(opt, device),
        src_vocab_size = model_opt.src_vocab_size,
        d_word_vec = model_opt.d_word_vec,
        beam_size=opt.beam_size,
        max_seq_len=opt.max_seq_len,
        src_pad_idx=opt.src_pad_idx,
        trg_pad_idx=opt.trg_pad_idx,
        trg_bos_idx=opt.trg_bos_idx,
        trg_eos_idx=opt.trg_eos_idx).to(device)

    unk_idx = SRC.vocab.stoi[SRC.unk_token]
    with open(os.path.join(opt.output, opt.file_name), 'w') as f:
        for example in tqdm(test_loader, mininterval=2, desc='  - (Test)', leave=False):
            src_seq = [SRC.vocab.stoi.get(word, unk_idx) for word in example.src]
            # print("src_seq", src_seq)
            pred_seq = translator.translate_sentence(torch.LongTensor([src_seq]).to(device))
            pred_line = ' '.join(TRG.vocab.itos[idx] for idx in pred_seq)
            pred_line = pred_line.replace(Constants.BOS_WORD, '').replace(Constants.EOS_WORD, '')
            f.write(pred_line.strip() + '\n')

    print('[Info] Finished.')

if __name__ == "__main__":
    '''
    Usage: python translate.py -model trained.chkpt -data multi30k.pt -no_cuda
    '''
    main()
