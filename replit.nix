{ pkgs, ... }: {
  deps = [
    pkgs.python311Full
    pkgs.python311Packages.pip
    pkgs.git
  ];

  env = {
    PYTHONPATH = "/home/runner/$REPL_SLUG";
    PYTHONUNBUFFERED = "1";
    FLASK_APP = "app.py";
    PORT = "5000";
  };
}