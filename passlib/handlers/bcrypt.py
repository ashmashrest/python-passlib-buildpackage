"""passlib.bcrypt

Implementation of OpenBSD's BCrypt algorithm.

PassLib will use the py-bcrypt package if it is available,
otherwise it will fall back to a slower builtin pure-python implementation.

Note that rounds must be >= 10 or an error will be returned.
"""
#=========================================================
#imports
#=========================================================
from __future__ import with_statement, absolute_import
#core
import re
import logging; log = logging.getLogger(__name__)
from warnings import warn
#site
try:
    from bcrypt import hashpw as pybcrypt_hashpw
except ImportError: #pragma: no cover - though should run whole suite w/o pybcrypt installed
    pybcrypt_hashpw = None
try:
    from bcryptor.engine import Engine as bcryptor_engine
except ImportError: #pragma: no cover - though should run whole suite w/o bcryptor installed
    bcryptor_engine = None
#libs
from passlib.utils import safe_os_crypt, classproperty, handlers as uh, \
    h64, to_hash_str, rng, getrandstr, bytes

#pkg
#local
__all__ = [
    "bcrypt",
]

# base64 character->value mapping used by bcrypt.
# this is same as as H64_CHARS, but the positions are different.
BCHARS = u"./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

# last bcrypt salt char should have 4 padding bits set to 0.
# thus, only the following chars are allowed:
BSLAST = u".Oeu"
BHLAST = u'.CGKOSWaeimquy26'

#=========================================================
#handler
#=========================================================
class bcrypt(uh.HasManyIdents, uh.HasRounds, uh.HasSalt, uh.HasManyBackends, uh.GenericHandler):
    """This class implements the BCrypt password hash, and follows the :ref:`password-hash-api`.

    It supports a fixed-length salt, and a variable number of rounds.

    The :meth:`encrypt()` and :meth:`genconfig` methods accept the following optional keywords:

    :param salt:
        Optional salt string.
        If not specified, one will be autogenerated (this is recommended).
        If specified, it must be 22 characters, drawn from the regexp range ``[./0-9A-Za-z]``.

    :param rounds:
        Optional number of rounds to use.
        Defaults to 12, must be between 4 and 31, inclusive.
        This value is logarithmic, the actual number of iterations used will be :samp:`2**{rounds}`.

    :param ident:
        selects specific version of BCrypt hash that will be used.
        Typically you want to leave this alone, and let it default to ``2a``,
        but it can be set to ``2`` to use the older version of BCrypt.

    It will use the first available of three possible backends:

    1. `py-bcrypt <http://www.mindrot.org/projects/py-bcrypt/>`_, if installed.
    2. `bcryptor <https://bitbucket.org/ares/bcryptor/overview>`_, if installed.
    3. stdlib's :func:`crypt.crypt()`, if the host OS supports BCrypt (eg: BSD).
    
    If no backends are available at runtime,
    :exc:`~passlib.utils.MissingBackendError` will be raised
    whenever :meth:`encrypt` or :meth:`verify` are called.
    You can see which backend is in use by calling the
    :meth:`~passlib.utils.handlers.HasManyBackends.get_backend()` method.
    """

    #=========================================================
    #class attrs
    #=========================================================
    #--GenericHandler--
    name = "bcrypt"
    setting_kwds = ("salt", "rounds", "ident")
    checksum_size = 31
    checksum_chars = BCHARS

    #--HasManyIdents--
    default_ident = u"$2a$"
    ident_values = (u"$2$", u"$2a$")
    ident_aliases = {u"2": u"$2$", u"2a": u"$2a$"}

    #--HasSalt--
    min_salt_size = max_salt_size = 22
    salt_chars = BCHARS
    #NOTE: 22nd salt char must be in BSLAST, not full BCHARS

    #--HasRounds--
    default_rounds = 12 #current passlib default
    min_rounds = 4 # bcrypt spec specified minimum
    max_rounds = 31 # 32-bit integer limit (since real_rounds=1<<rounds)
    rounds_cost = "log2"

    #=========================================================
    #formatting
    #=========================================================

    @classmethod
    def from_string(cls, hash, strict=True):
        if not hash:
            raise ValueError("no hash specified")
        if isinstance(hash, bytes):
            hash = hash.decode("ascii")
        for ident in cls.ident_values:
            if hash.startswith(ident):
                break
        else:
            raise ValueError("invalid bcrypt hash")
        rounds, data = hash[len(ident):].split(u"$")
        rval = int(rounds)
        if strict and rounds != u'%02d' % (rval,):
            raise ValueError("invalid bcrypt hash (no rounds padding)")
        salt, chk = data[:22], data[22:]
        return cls(
            rounds=rval,
            salt=salt,
            checksum=chk or None,
            ident=ident,
            strict=strict and bool(chk),
        )

    def to_string(self, native=True):
        hash = u"%s%02d$%s%s" % (self.ident, self.rounds, self.salt, self.checksum or u'')
        return to_hash_str(hash) if native else hash

    #=========================================================
    # specialized salt generation - fixes passlib issue 25
    #=========================================================

    @classmethod
    def _hash_needs_update(cls, hash, **opts):
        if isinstance(hash, bytes):
            hash = hash.decode("ascii")
        if hash.startswith(u"$2a$") and hash[28] not in BSLAST:
            return True
        return False

    @classmethod
    def normhash(cls, hash):
        "helper to normalize hash, correcting any bcrypt padding bits"
        if cls.identify(hash):
            return cls.from_string(hash, strict=False).to_string()
        else:
            return hash

    @classmethod
    def generate_salt(cls, salt_size=None, strict=False):
        assert cls.min_salt_size == cls.max_salt_size == cls.default_salt_size == 22
        if salt_size is not None and salt_size != 22:
            raise ValueError("bcrypt salts must be 22 characters in length")
        return getrandstr(rng, BCHARS, 21) + getrandstr(rng, BSLAST, 1)

    @classmethod
    def norm_salt(cls, *args, **kwds):
        salt = super(bcrypt, cls).norm_salt(*args, **kwds)
        if salt and salt[-1] not in BSLAST:
            salt = salt[:-1] + BCHARS[BCHARS.index(salt[-1]) & ~15]
            assert salt[-1] in BSLAST
            warn(
                "encountered a bcrypt hash with incorrectly set padding bits; "
                "you may want to use bcrypt.normhash() "
                "to fix this; see Passlib 1.5.3 changelog."
                )
        return salt

    @classmethod
    def norm_checksum(cls, *args, **kwds):
        checksum = super(bcrypt, cls).norm_checksum(*args, **kwds)
        if checksum and checksum[-1] not in BHLAST:
            checksum = checksum[:-1] + BCHARS[BCHARS.index(checksum[-1]) & ~3]
            assert checksum[-1] in BHLAST
            warn(
                "encountered a bcrypt hash with incorrectly set padding bits; "
                "you may want to use bcrypt.normhash() "
                "to fix this; see Passlib 1.5.3 changelog."
                )
        return checksum
    
    #=========================================================
    #primary interface
    #=========================================================
    backends = ("pybcrypt", "bcryptor", "os_crypt")

    @classproperty
    def _has_backend_pybcrypt(cls):
        return pybcrypt_hashpw is not None

    @classproperty
    def _has_backend_bcryptor(cls):
        return bcryptor_engine is not None

    @classproperty
    def _has_backend_os_crypt(cls):
        h1 = u'$2$04$......................1O4gOrCYaqBG3o/4LnT2ykQUt1wbyju'
        h2 = u'$2a$04$......................qiOQjkB8hxU8OzRhS.GhRMa4VUnkPty'
        return bool(safe_os_crypt and safe_os_crypt(u"test",h1)[1]==h1 and
                    safe_os_crypt(u"test", h2)[1]==h2)

    @classmethod
    def _no_backends_msg(cls):
        return "no BCrypt backends available - please install pybcrypt or bcryptor for BCrypt support"

    def _calc_checksum_os_crypt(self, secret):
        ok, hash = safe_os_crypt(secret, self.to_string(native=False))
        if ok:
            return hash[-31:]
        else:
            #NOTE: not checking backends since this is lowest priority,
            #      so they probably aren't available either
            raise ValueError("encoded password can't be handled by os_crypt"
                             " (recommend installing pybcrypt or bcryptor)")

    def _calc_checksum_pybcrypt(self, secret):
        #pybcrypt behavior:
        #   py2: unicode secret -> ascii bytes (we override this)
        #        unicode hash -> ascii bytes (we provide ascii bytes)
        #        returns ascii bytes
        #   py3: can't get to install
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        hash = pybcrypt_hashpw(secret,
                               self.to_string(native=False))
        return hash[-31:].decode("ascii")

    def _calc_checksum_bcryptor(self, secret):
        #bcryptor behavior:
        #   py2: unicode secret -> ascii bytes (we have to override)
        #        unicode hash -> ascii bytes (we provide ascii bytes)
        #        returns ascii bytes
        #   py3: can't get to install
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        hash = bcryptor_engine(False).hash_key(secret,
                                               self.to_string(native=False))
        return hash[-31:].decode("ascii")

    #=========================================================
    #eoc
    #=========================================================

#=========================================================
#eof
#=========================================================
