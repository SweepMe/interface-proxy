# interface-proxy
A library that allows to import a module in one process (server) and use that module in another process (client).

## Use Cases
- You want to run your application on one computer, but a python module shall be run on another computer (remote control).
- You need to use a library which has conflicting dependencies with other components used by your application (DLL Hell), or is only available for another bitness.

## Features and Limitations
- The python module in the server can be used transparently, as if the module was imported on the client.
- Only primitive attributes and function calls are supported. Instantiating objects or calling methods on objects does not work and requires a wrapper on the server.
- Objects can be referenced and these references can be passed to functions as arguments.
- Client can automatically start and terminate the server if running on the same machine.
- **No Authentication support. When the computer can be reached from the outside, make sure your firewall only grants access from trusted sources.**
- Only supports Windows as OS

## Communication Protocols
- Via named pipes (client and server on the same machine).
- Via TCP connection

## Examples
You can check the integration tests in the source code to find out how to use this library.
If you are interested in a collaborative project to evaluate the use of this library and implement it
in your application, feel free to contact us at <contact@sweep-me.net>.
