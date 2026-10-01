#import <Foundation/Foundation.h>
#import "XADArchiveParser.h"
#import "XADException.h"
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#include <stdio.h>

// Decoder-only process: archive paths never become destination filesystem paths.
static volatile LONG stopped = 0;
static BOOL passwordMissing = NO;
static NSString *password = nil;
static HANDLE input;
static NSUInteger checkedForks = 0, uncheckedForks = 0;
static NSNumber *activeId = nil;
static NSString *activePart = nil;
static void sendEvent(NSDictionary *object) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:&error];
    if (!data)
        ExitProcess(2);
    fwrite([data bytes], 1, [data length], stdout);
    fputc('\n', stdout);
    fflush(stdout);
}
static void fail(NSString *code, NSString *message) {
    @throw [NSException exceptionWithName:code reason:message userInfo:nil];
}
static NSData *readLine(void) {
    NSMutableData *line = [NSMutableData data];
    unsigned char c;
    DWORD n;
    while (ReadFile(input, &c, 1, &n, NULL) && n) {
        if (c == '\n')
            return line;
        [line appendBytes:&c length:1];
        if ([line length] > 1024 * 1024)
            fail(@"protocol_error", @"Request exceeds size limit");
    }
    return nil;
}
static DWORD WINAPI cancellationReader(void *unused) {
    for (;;) {
        NSAutoreleasePool *pool = [NSAutoreleasePool new];
        NSData *line = readLine();
        if (!line) {
            [pool release];
            break;
        }
        NSDictionary *obj = [NSJSONSerialization JSONObjectWithData:line options:0 error:NULL];
        if ([[obj objectForKey:@"cancel"] boolValue])
            InterlockedExchange(&stopped, 1);
        [pool release];
    }
    return 0;
}
static void checkStop(void) {
    if (stopped)
        fail(@"cancelled", @"Cancelled");
}

@interface Collector : NSObject {
  @public
    NSMutableArray *entries;
}
@end
@implementation Collector
- (id)init {
    if ((self = [super init]))
        entries = [NSMutableArray new];
    return self;
}
- (void)dealloc {
    [entries release];
    [super dealloc];
}
- (void)archiveParser:(XADArchiveParser *)parser foundEntryWithDictionary:(NSDictionary *)entry {
    [entries addObject:entry];
}
- (BOOL)archiveParsingShouldStop:(XADArchiveParser *)parser {
    return stopped != 0;
}
- (void)archiveParserNeedsPassword:(XADArchiveParser *)parser {
    if (!password) {
        passwordMissing = YES;
        [XADException raisePasswordException];
    }
    [parser setPassword:password];
}
@end

static NSString *filenameEncoding = nil;
static NSArray *parse(XADArchiveParser *parser) {
    checkStop();
    NSString *format = [parser formatName];
    if (filenameEncoding)
        [parser setEncodingName:filenameEncoding];
    else if ([format isEqual:@"BinHex"] || [format isEqual:@"MacBinary"] ||
             [NSStringFromClass([parser class]) isEqual:@"XADStuffItParser"] ||
             [NSStringFromClass([parser class]) isEqual:@"XADStuffIt5Parser"])
        [parser setEncodingName:XADMacOSRomanStringEncodingName];
    Collector *collector = [Collector new];
    [parser setDelegate:collector];
    if (password)
        [parser setPassword:password];
    XADError error = [parser parseWithoutExceptions];
    NSArray *entries = [[collector->entries copy] autorelease];
    [parser setDelegate:nil];
    [collector release];
    checkStop();
    if (passwordMissing)
        fail(@"password_required", @"Password required");
    if (error)
        fail(@"parse_error",
             [NSString stringWithFormat:@"Legacy archive parsing failed (XAD %d)", error]);
    return entries;
}
static NSString *pathName(NSDictionary *entry) {
    XADPath *path = [entry objectForKey:XADFileNameKey];
    return [[path pathComponents] componentsJoinedByString:@"/"];
}
// XADPath.data omits the current part when a parent exists. Keep the leaf's
// original bytes in our mapping without changing the frozen engine source.
@interface XADPath (PacksmithRawName)
- (void)packsmithAppendRawName:(NSMutableData *)data;
- (NSData *)packsmithRawName;
- (void)packsmithRawComponents:(NSMutableArray *)parts;
@end
@implementation XADPath (PacksmithRawName)
- (void)packsmithAppendRawName:(NSMutableData *)data {
    if (parent) {
        [parent packsmithAppendRawName:data];
        [data appendBytes:"/" length:1];
    }
    if (![self _isPartAbsolute])
        [self _appendPathForPartToData:data];
}
- (NSData *)packsmithRawName {
    NSMutableData *data = [NSMutableData data];
    [self packsmithAppendRawName:data];
    return [NSData dataWithData:data];
}
- (void)packsmithRawComponents:(NSMutableArray *)parts {
    if (parent) [parent packsmithRawComponents:parts];
    if ([self _isPartEmpty]) return;
    NSMutableArray *decoded = [NSMutableArray array];
    [self _addPathComponentsOfPartToArray:decoded encodingName:[self encodingName]];
    NSMutableData *raw = [NSMutableData data];
    [self _appendPathForPartToData:raw];
    if ([decoded count] == 1) [parts addObject:[raw base64EncodedStringWithOptions:0]];
    else for (id unused in decoded) { (void)unused; [parts addObject:[NSNull null]]; }
}
@end
static BOOL flag(NSDictionary *entry, NSString *key) {
    return [[entry objectForKey:key] boolValue];
}
static NSNumber *bytes(NSDictionary *entry) {
    return [entry objectForKey:XADFileSizeKey] ?: @0;
}
static BOOL forkPair(XADArchiveParser *parser, NSDictionary *resource, NSDictionary *data) {
    if (!resource || !data)
        return NO;
    NSString *className = NSStringFromClass([parser class]);
    if ([className isEqual:@"XADStuffItParser"] || [className isEqual:@"XADStuffIt5Parser"]) {
        long long end = [[resource objectForKey:XADDataOffsetKey] longLongValue] +
                        [[resource objectForKey:XADDataLengthKey] longLongValue];
        if ([className isEqual:@"XADStuffItParser"] && [resource objectForKey:@"StuffItEntryKey"])
            end += 16;
        return end == [[data objectForKey:XADDataOffsetKey] longLongValue];
    }
    NSNumber *token = [resource objectForKey:@"StuffItXID"];
    if (token)
        return [token isEqual:[data objectForKey:@"StuffItXID"]];
    return [[parser formatName] isEqual:@"BinHex"] || [[parser formatName] isEqual:@"MacBinary"];
}

static void readFork(XADArchiveParser *parser, NSDictionary *entry, NSUInteger index,
                     NSString *part, BOOL output) {
    activeId = @(index); activePart = part;
    sendEvent(@{@"event": @"progress", @"phase": @"decoding", @"id": activeId, @"part": part});
    checkStop();
    if (flag(entry, XADIsCorruptedKey))
        fail(@"integrity_failed", @"Entry is marked corrupt");
    if (flag(entry, XADIsEncryptedKey) && !password)
        fail(@"password_required", @"Password required");
    Collector *collector = [Collector new];
    [parser setDelegate:collector];
    @try {
        CSHandle *handle = [parser handleForEntryWithDictionary:entry wantChecksum:YES];
        if (!handle)
            fail(@"unsupported_codec", @"Legacy codec cannot decode this fork");
        if (output)
            sendEvent(@{@"event" : @"begin", @"id" : @(index), @"part" : part});
        unsigned char buffer[65536];
        unsigned long long count = 0;
        for (;;) {
            checkStop();
            int n = [handle readAtMost:sizeof(buffer) toBuffer:buffer];
            if (!n)
                break;
            if (n < 0)
                fail(@"decode_failed", @"Invalid legacy stream length");
            count += n;
            if (output) {
                NSAutoreleasePool *pool = [NSAutoreleasePool new];
                NSData *data = [NSData dataWithBytes:buffer length:n];
                sendEvent(@{
                    @"event" : @"chunk",
                    @"id" : @(index),
                    @"part" : part,
                    @"data" : [data base64EncodedStringWithOptions:0]
                });
                [pool release];
            }
        }
        BOOL checksum = [handle hasChecksum];
        sendEvent(@{@"event": @"progress", @"phase": @"verifying", @"id": activeId, @"part": part});
        if (checksum && ![handle isChecksumCorrect])
            fail(@"integrity_failed", @"Legacy fork checksum failed");
        NSNumber *size = [entry objectForKey:XADFileSizeKey];
        if (size && [size unsignedLongLongValue] != count)
            fail(@"integrity_failed", @"Legacy fork size differs from archive metadata");
        if (checksum)
            checkedForks++;
        else
            uncheckedForks++;
        if (output)
            sendEvent(@{
                @"event" : @"end",
                @"id" : @(index),
                @"part" : part,
                @"checksum_checked" : [NSNumber numberWithBool:checksum],
                @"bytes" : [NSString stringWithFormat:@"%llu", count]
            });
    } @finally {
        [parser setDelegate:nil];
        [collector release];
    }
}

int main(void) {
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    input = GetStdHandle(STD_INPUT_HANDLE);
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    int result = 0;
    @try {
        NSData *line = readLine();
        if (!line)
            fail(@"protocol_error", @"Missing request");
        NSDictionary *request = [NSJSONSerialization JSONObjectWithData:line options:0 error:NULL];
        if (![request isKindOfClass:[NSDictionary class]] ||
            [[request objectForKey:@"protocol"] intValue] != 1)
            fail(@"protocol_error", @"Unsupported legacy protocol");
        password = [[request objectForKey:@"password"] copy];
        filenameEncoding = [[request objectForKey:@"filename_encoding"] copy];
        if (filenameEncoding) {
            BOOL known = NO;
            for (NSArray *encoding in [XADString availableEncodingNames])
                for (NSUInteger i = 1; i < [encoding count]; ++i)
                    if ([[encoding objectAtIndex:i] caseInsensitiveCompare:filenameEncoding] ==
                        NSOrderedSame)
                        known = YES;
            if (!known)
                fail(@"unsupported_encoding", @"Filename encoding is unavailable");
        }
        HANDLE thread = CreateThread(NULL, 0, cancellationReader, NULL, 0, NULL);
        if (thread)
            CloseHandle(thread);
        XADError openError = 0;
        XADArchiveParser *parser =
            [XADArchiveParser archiveParserForPath:[request objectForKey:@"archive"]
                                             error:&openError];
        if (!parser)
            fail(@"open_failed",
                 [NSString stringWithFormat:@"Unsupported or damaged legacy archive (XAD %d)",
                                            openError]);
        NSString *outer = [parser formatName];
        BOOL supported =
            [outer rangeOfString:@"StuffIt" options:NSCaseInsensitiveSearch].location !=
                NSNotFound ||
            [outer isEqual:@"BinHex"] || [outer isEqual:@"MacBinary"];
        if (!supported)
            fail(@"unsupported_format",
                 @"This legacy adapter supports StuffIt, BinHex and MacBinary");
        NSArray *entries = nil;
        NSMutableArray *wrappers = [NSMutableArray array];
        for (int depth = 0;; ++depth) {
            if (depth >= 8)
                fail(@"nesting_limit", @"Legacy wrapper nesting limit exceeded");
            entries = parse(parser);
            NSDictionary *data = nil, *resource = nil;
            if ([entries count] <= 2)
                for (NSDictionary *entry in entries) {
                    if (flag(entry, XADIsResourceForkKey))
                        resource = entry;
                    else if (!flag(entry, XADIsDirectoryKey))
                        data = entry;
                }
            if (data && flag(data, XADIsArchiveKey) &&
                (!resource || [pathName(data) isEqual:pathName(resource)])) {
                XADError error = 0;
                XADArchiveParser *inner =
                    [XADArchiveParser archiveParserForEntryWithDictionary:data
                                                   resourceForkDictionary:resource
                                                            archiveParser:parser
                                                             wantChecksum:YES
                                                                    error:&error];
                if (!inner)
                    fail(@"wrapper_error",
                         [NSString stringWithFormat:@"Cannot open wrapped legacy archive (XAD %d)",
                                                    error]);
                NSString *innerFormat = [inner formatName];
                if ([innerFormat rangeOfString:@"StuffIt" options:NSCaseInsensitiveSearch]
                            .location == NSNotFound &&
                    ![innerFormat isEqual:@"BinHex"] && ![innerFormat isEqual:@"MacBinary"])
                    break;
                [wrappers addObject:@{
                    @"parser" : parser,
                    @"data" : data,
                    @"resource" : resource ?: [NSNull null]
                }];
                parser = inner;
            } else
                break;
        }
        NSMutableArray *groups = [NSMutableArray array];
        NSMutableDictionary *lastByPath = [NSMutableDictionary dictionary];
        for (NSDictionary *entry in entries) {
            NSString *path = pathName(entry);
            BOOL fork = flag(entry, XADIsResourceForkKey), dir = flag(entry, XADIsDirectoryKey);
            NSMutableDictionary *group = nil;
            if (!dir) {
                NSMutableDictionary *candidate = [lastByPath objectForKey:path];
                if (candidate && ![candidate objectForKey:(fork ? @"resource" : @"data")] &&
                    [candidate objectForKey:(fork ? @"data" : @"resource")] &&
                    forkPair(parser, fork ? entry : [candidate objectForKey:@"resource"],
                             fork ? [candidate objectForKey:@"data"] : entry)) {
                    group = candidate;
                }
            }
            if (!group) {
                group = [NSMutableDictionary dictionaryWithObjectsAndKeys:path, @"path", nil];
                [groups addObject:group];
            }
            if (!dir)
                [lastByPath setObject:group forKey:path];
            [group setObject:entry forKey:fork ? @"resource" : @"data"];
        }
        NSMutableArray *metadata = [NSMutableArray array];
        NSUInteger index = 0;
        for (NSDictionary *group in groups) {
            NSDictionary *data = [group objectForKey:@"data"],
                         *resource = [group objectForKey:@"resource"], *main = data ?: resource;
            NSData *finder = [parser finderInfoForDictionary:main];
            NSMutableArray *rawParts = [NSMutableArray array];
            [[main objectForKey:XADFileNameKey] packsmithRawComponents:rawParts];
            NSMutableDictionary *row = [NSMutableDictionary dictionaryWithDictionary:@{
                @"id" : @(index++),
                @"path" : [group objectForKey:@"path"],
                @"components" : [[main objectForKey:XADFileNameKey] pathComponents],
                @"raw_components" : rawParts,
                @"absolute" : @([[main objectForKey:XADFileNameKey] isAbsolute]),
                @"size" : [bytes(data) stringValue],
                @"resource_size" : [bytes(resource) stringValue],
                @"directory" : @(flag(main, XADIsDirectoryKey)),
                @"encrypted" :
                    @(flag(data, XADIsEncryptedKey) || flag(resource, XADIsEncryptedKey)),
                @"link" : @(flag(main, XADIsLinkKey) || flag(main, XADIsHardLinkKey) ||
                            flag(main, XADIsFIFOKey) || flag(main, XADIsCharacterDeviceKey) ||
                            flag(main, XADIsBlockDeviceKey)),
                @"has_data" : @(data != nil),
                @"has_resource" : @(resource != nil),
                @"finder_info" : finder ? [finder base64EncodedStringWithOptions:0] : @"",
                @"raw_name" : [[[main objectForKey:XADFileNameKey] packsmithRawName]
                    base64EncodedStringWithOptions:0],
                @"encoding" : [[main objectForKey:XADFileNameKey] encodingName] ?: @"unknown"
            }];
            [row setObject:([[data objectForKey:XADCompressionNameKey] description] ?: @"unknown") forKey:@"data_method"];
            [row setObject:([[resource objectForKey:XADCompressionNameKey] description] ?: @"unknown") forKey:@"resource_method"];
            NSDate *modified = [main objectForKey:XADLastModificationDateKey];
            if (modified)
                [row setObject:@((long long)([modified timeIntervalSince1970] * 1000))
                        forKey:@"modified_ms"];
            for (NSString *key in @[@"PacksmithCreated1904", @"PacksmithModified1904"])
                if ([main objectForKey:key]) [row setObject:[main objectForKey:key] forKey:[key isEqual:@"PacksmithCreated1904"] ? @"created_1904" : @"modified_1904"];
            for (NSString *key in @[
                     @"link", @"absolute", @"encrypted", @"directory", @"has_data", @"has_resource"
                 ])
                [row setObject:[NSNumber numberWithBool:[[row objectForKey:key] boolValue]]
                        forKey:key];
            [metadata addObject:row];
            if ([metadata count] == 500) {
                sendEvent(@{@"event" : @"entries", @"items" : metadata});
                [metadata removeAllObjects];
            }
        }
        if ([metadata count])
            sendEvent(@{@"event" : @"entries", @"items" : metadata});
        sendEvent(@{
            @"event" : @"ready",
            @"count" : @([groups count]),
            @"format" : [parser formatName],
            @"outer_format" : outer
        });
        NSString *operation = [request objectForKey:@"operation"];
        if (![operation isEqual:@"list"]) {
            NSMutableIndexSet *selected = [NSMutableIndexSet indexSet];
            id requestedIds = [request objectForKey:@"ids"];
            if (!requestedIds || requestedIds == [NSNull null]) requestedIds = @[];
            if (![requestedIds isKindOfClass:[NSArray class]]) fail(@"invalid_selection", @"Entry IDs must be an array");
            for (NSNumber *id in requestedIds) {
                if ([id longLongValue] < 0 || [id unsignedLongLongValue] >= [groups count])
                    fail(@"invalid_id", @"Invalid legacy entry ID");
                [selected addIndex:[id unsignedIntegerValue]];
            }
            if (![selected count])
                [selected addIndexesInRange:NSMakeRange(0, [groups count])];
            NSMutableArray *folders = [NSMutableArray array];
            for (NSUInteger i = [selected firstIndex]; i != NSNotFound;
                 i = [selected indexGreaterThanIndex:i]) {
                NSDictionary *group = [groups objectAtIndex:i];
                if (flag([group objectForKey:@"data"], XADIsDirectoryKey))
                    [folders addObject:[[[group objectForKey:@"data"] objectForKey:XADFileNameKey]
                                           pathComponents]];
            }
            index = 0;
            for (NSDictionary *group in groups) {
                NSDictionary *main =
                    [group objectForKey:@"data"] ?: [group objectForKey:@"resource"];
                NSArray *components = [[main objectForKey:XADFileNameKey] pathComponents];
                for (NSArray *folder in folders)
                    if ([components count] > [folder count] &&
                        [[components subarrayWithRange:NSMakeRange(0, [folder count])]
                            isEqual:folder])
                        [selected addIndex:index];
                index++;
            }
            for (NSUInteger i = [selected firstIndex]; i != NSNotFound;
                 i = [selected indexGreaterThanIndex:i]) {
                NSDictionary *group = [groups objectAtIndex:i],
                             *data = [group objectForKey:@"data"],
                             *resource = [group objectForKey:@"resource"];
                if (data && !flag(data, XADIsDirectoryKey))
                    readFork(parser, data, i, @"data", [operation isEqual:@"stream"]);
                if (resource)
                    readFork(parser, resource, i, @"resource", [operation isEqual:@"stream"]);
                sendEvent(@{@"event" : @"verified", @"id" : @(i)});
            }
            // Outer fork handles share the nested parser's source. Verify the inner
            // source before opening wrapper handles, which reposition that source.
            XADError checksum = [parser testChecksumWithoutExceptions];
            if (checksum)
                fail(@"integrity_failed", @"Legacy archive checksum failed");
            for (NSDictionary *wrapper in [wrappers reverseObjectEnumerator]) {
                readFork([wrapper objectForKey:@"parser"], [wrapper objectForKey:@"data"], 0,
                         @"wrapper", NO);
                if ([wrapper objectForKey:@"resource"] != [NSNull null])
                    readFork([wrapper objectForKey:@"parser"], [wrapper objectForKey:@"resource"],
                             0, @"wrapper", NO);
            }
        }
        checkStop();
        sendEvent(@{
            @"event" : @"complete",
            @"checked_forks" : @(checkedForks),
            @"unchecked_forks" : @(uncheckedForks),
            @"expanded_wrappers" : @([wrappers count])
        });
    } @catch (NSException *error) {
        NSString *code = passwordMissing ? @"password_required"
                         : stopped       ? @"cancelled"
                                         : [error name];
        NSString *message = passwordMissing ? @"Password required"
                            : stopped       ? @"Cancelled"
                                            : [error reason];
        sendEvent(@{
            @"event" : stopped ? @"cancelled" : @"error",
            @"code" : code,
            @"id": activeId ?: @(-1), @"part": activePart ?: @"",
            @"message" : message ?: @"Legacy decoding failed"
        });
        result = 1;
    }
    [pool release];
    ExitProcess(result);
}
