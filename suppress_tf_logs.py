"""
Utility script to override and suppress TensorFlow's GPU/CUDA warnings.
This should be imported before any other imports in the main script.
"""

import os
import sys
import logging

# Configure environment variables to completely suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # 0=DEBUG, 1=INFO, 2=WARNING, 3=ERROR
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'  # Force CPU-only mode
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_ENABLE_MLIR_BRIDGE'] = '0'
os.environ['TF_ENABLE_MLIR_GRAPH_OPTIMIZATION'] = '0'
os.environ['TF_ENABLE_GPU_GARBAGE_COLLECTION'] = 'false'

# Utility function to suppress standard output during imports
def suppress_stdout():
    """Context manager to temporarily suppress stdout."""
    class NullDevice:
        def write(self, s): pass
        def flush(self): pass
        def close(self): pass  # Add close method to prevent exit errors
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = NullDevice()
    sys.stderr = NullDevice()
    return old_stdout, old_stderr

# Utility function to restore standard output
def restore_stdout(old_stdout, old_stderr):
    """Restore the original stdout and stderr."""
    sys.stdout = old_stdout
    sys.stderr = old_stderr

# Suppress warnings at the Python level
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*tensor.*')
warnings.filterwarnings('ignore', message='.*cuda.*')
warnings.filterwarnings('ignore', message='.*cublas.*')

# Monkey patch TensorFlow's logging system (advanced approach)
def silence_tensorflow():
    """Completely silence TensorFlow's logging."""
    try:
        # Try to import TensorFlow silently
        import tensorflow as tf

        # Control Python-level logging using standard logging module
        logging.getLogger('tensorflow').setLevel(logging.ERROR)

        # Handle TF2 specific settings gracefully
        if hasattr(tf, 'autograph'):
            try:
                tf.autograph.set_verbosity(1) # Set to 1 for less noise (0=silent, 1=brief, 2=normal, 3=verbose)
            except AttributeError:
                pass # Ignore if set_verbosity isn't available
        
        if hasattr(tf, 'debugging'):
            try:
                tf.debugging.set_log_device_placement(False)
            except AttributeError:
                pass # Ignore if set_log_device_placement isn't available

        return True
    except ImportError:
        return False

if __name__ == "__main__":
    print("TensorFlow logging suppression utilities loaded.")
    print("Environment variables set:")
    for env_var in ['TF_CPP_MIN_LOG_LEVEL', 'CUDA_VISIBLE_DEVICES', 
                   'TF_FORCE_GPU_ALLOW_GROWTH', 'TF_ENABLE_ONEDNN_OPTS',
                   'TF_ENABLE_MLIR_BRIDGE', 'TF_ENABLE_MLIR_GRAPH_OPTIMIZATION']:
        print(f"  {env_var} = {os.environ.get(env_var, 'Not set')}")
    
    # Test by importing TensorFlow
    print("\nTesting TensorFlow import silencing...")
    old_stdout, old_stderr = suppress_stdout()
    silence_tensorflow()
    restore_stdout(old_stdout, old_stderr)
    print("TensorFlow imported successfully with warnings suppressed.") 