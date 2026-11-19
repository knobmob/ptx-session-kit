# ptx-session-kit
decode and encode protools session file format (.ptx), soundCraft export (feasibility study)


### Legal & Interoperability Disclaimer

**Important Note:** This project is not affiliated with, maintained, authorized, endorsed, or sponsored by [Avid Technology, Inc.] or any of its affiliates. All product and company names are the registered trademarks of their original owners. The use of any trade name or trademark is for identification and reference purposes only.

**Purpose of this Project (Interoperability)**
This software was developed completely independently and is published solely for the purpose of enabling **interoperability** between independently created computer programs and the [Pro Tools Session (.ptx)] file format. This is explicitly permitted under Article 6 of the European Union Directive 2009/24/EC on the legal protection of computer programs, as well as Section 69e of the German Copyright Act (UrhG) and similar international fair-use exemptions.

**No DRM Circumvention**
The target file format utilizes a basic XOR data obfuscation technique, primarily functioning as a vendor lock-in mechanism rather than a cryptographic security measure. This tool merely parses and de-obfuscates this binary structure to allow users to read and write their own independently created data.
**This tool does not bypass, decrypt, or circumvent any Digital Rights Management (DRM) systems or "effective technological measures" designed to protect copyrighted works.**

**Clean-Room Reverse Engineering**
All code in this repository was written from scratch based on legitimate black-box analysis and observation of the file structure. It does **not**:

* Contain any leaked, proprietary source code of the original manufacturer.
* Contain any stolen cryptographic master keys or trade secrets.
* Include or distribute any copyrighted assets, demo files, or proprietary intellectual property belonging to the original manufacturer. Any test files provided in this repository are 100% independently created from scratch.

**Liability**
This software is provided "as is", without warranty of any kind, express or implied. The authors shall not be liable for any claims, damages, or other liability arising from, out of, or in connection with the software or the use or other dealings in the software. Users are solely responsible for ensuring their use of this tool complies with their local laws and applicable end-user license agreements.
