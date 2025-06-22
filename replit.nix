{ pkgs, ... }: {
  deps = [
    pkgs.python311Full
    pkgs.python311Packages.pip
    pkgs.python311Packages.virtualenv
    pkgs.awscli2
    pkgs.jq
    pkgs.git
    pkgs.openssl
    pkgs.zlib
    pkgs.stdenv.cc.cc.lib
  ];

  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
      pkgs.openssl
    ];
    PYTHONHOME = "${pkgs.python311Full}";
    PYTHONBIN = "${pkgs.python311Full}/bin/python3.11";
    LANG = "en_US.UTF-8";
    
    # AWS Configuration
    AWS_CONFIG_FILE = "/home/runner/${builtins.baseNameOf ./.}/.aws/config";
    AWS_SHARED_CREDENTIALS_FILE = "/home/runner/${builtins.baseNameOf ./.}/.aws/credentials";
    
    # Python configuration
    PYTHONPATH = "/home/runner/${builtins.baseNameOf ./.}";
    PYTHONUNBUFFERED = "1";
    
    # Flask configuration
    FLASK_APP = "app.py";
    FLASK_ENV = "development";
    
    # Port configuration
    PORT = "5000";
  };
  
  # Enable non-free packages (required for some AWS tools)
  nixpkgs.config.allowUnfree = true;
}