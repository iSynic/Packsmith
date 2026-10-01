#import <Foundation/Foundation.h>
#include <stdio.h>
#include <sys/types.h>

int main(void) {
    NSAutoreleasePool *pool=[NSAutoreleasePool new];
    NSString *text=[NSString stringWithUTF8String:"caf\xc3\xa9-\xe6\x97\xa5\xe6\x9c\xac"];
    BOOL caught=NO;
    NSArray *classes=[NSArray arrayWithObjects:[NSString class],nil];
    BOOL membership=[classes containsObject:[NSString class]] && ![classes containsObject:[NSAutoreleasePool class]];
    BOOL unequal=![@"a" isEqual:@"b"];
    @try { [NSException raise:@"ProbeException" format:@"expected"]; }
    @catch(NSException *exception) { caught=[[exception name] isEqualToString:@"ProbeException"]; }
    const unsigned char *path=(const unsigned char *)[@"C:/probe" fileSystemRepresentation];
    printf("{\"unicode_length\":%lu,\"exception_caught\":%s,\"off_t_bytes\":%lu,\"bool_bytes\":%lu,\"class_membership_correct\":%s,\"unequal_strings_correct\":%s,\"filesystem_prefix_hex\":\"%02x%02x%02x%02x\"}\n",
        (unsigned long)[text length],caught?"true":"false",(unsigned long)sizeof(off_t),(unsigned long)sizeof(BOOL),membership?"true":"false",unequal?"true":"false",path[0],path[1],path[2],path[3]);
    BOOL ok=caught && [text length]==7 && sizeof(BOOL)==1 && membership && unequal && sizeof(off_t)==8;
    [pool release];return ok?0:1;
}
