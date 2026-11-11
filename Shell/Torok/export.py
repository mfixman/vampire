# Export the checkpoint to a tensor-only TorchScript module for LibTorch.
import argparse
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description = 'Export a ReLU Connections checkpoint for Vampire.')
    parser.add_argument('checkpoint', type = Path)
    parser.add_argument('output', type = Path)
    parser.add_argument('--connections', type = Path, required = True)
    args = parser.parse_args()
    root = args.connections.resolve()
    sys.path[:0] = [str(root / 'src'), str(root / 'packages')]
    from axiom_prediction.model import AxiomPredictor
    from axiom_prediction.torchscript import export_model
    model = AxiomPredictor.load(args.checkpoint, device = 'cpu').model
    if str(model.config.activation).lower() != 'relu':
        raise ValueError('This exporter supports ReLU models only')
    export_model(model).save(str(args.output))
    print(f'Exported {args.output}')

if __name__ == '__main__':
    main()
